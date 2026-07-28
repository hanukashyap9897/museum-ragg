import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.database.session import get_db
from app.models.document import Document, ProcessingStatus
from app.schemas.document import UploadResponse, DocumentResponse
from app.services.embedding_service import compute_document_embedding

router = APIRouter(prefix="/upload", tags=["Upload"])


def _validate_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Allowed: {settings.ALLOWED_EXTENSIONS}",
        )
    return ext


@router.post("/document", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Uploads a single document (PDF, image, or video), saves it to disk,
    and creates a Document row in Postgres with status = pending.

    title/tags/description are optional user-supplied metadata — these
    matter most for content OCR/ICR can't read (photos, videos), but are
    accepted for every upload since they also improve search on documents
    that DO get OCR/ICR text extracted.

    An initial embedding is computed immediately from whatever metadata
    is available at upload time (title/tags/description). Once OCR/ICR
    finishes (in the existing async pipeline), the embedding should be
    recomputed to also include that extracted text — see
    recompute_embedding_after_processing() in embedding_service usage
    within the OCR/ICR/IDP completion handlers.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    ext = _validate_extension(file.filename)

    doc_id = uuid.uuid4()
    stored_filename = f"{doc_id}{ext}"
    stored_path = settings.UPLOAD_DIR / stored_filename

    size_bytes = 0
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024

    try:
        with open(stored_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                size_bytes += len(chunk)
                if size_bytes > max_bytes:
                    stored_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=400,
                        detail=f"File too large. Max allowed size is {settings.MAX_FILE_SIZE_MB} MB.",
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}")

    final_title = title or file.filename

    embedding = compute_document_embedding(
        title=final_title,
        tags=tags,
        description=description,
        ocr_text=None,
        icr_text=None,
    )

    document = Document(
        id=doc_id,
        title=final_title,
        file_path=str(stored_path),
        file_type=ext.lstrip("."),
        ocr_status=ProcessingStatus.PENDING,
        icr_status=ProcessingStatus.PENDING,
        tags=tags,
        description=description,
        embedding=embedding,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    return UploadResponse(
        id=document.id,
        title=document.title,
        file_type=document.file_type,
        status="uploaded",
        message="File saved. OCR processing not started yet.",
    )


@router.get("/status/{document_id}", response_model=DocumentResponse)
def get_upload_status(document_id: uuid.UUID, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document
