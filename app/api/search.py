import mimetypes
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.database.session import get_db
from app.models.document import Document
from app.services.embedding_service import compute_embedding

router = APIRouter(prefix="/search", tags=["Search"])

MIME_TYPE_MAP = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
    "tiff": "image/tiff",
    "tif": "image/tiff",
    "txt": "text/plain",
    "mp4": "video/mp4",
    "webm": "video/webm",
    "mov": "video/quicktime",
    "avi": "video/x-msvideo",
    "mkv": "video/x-matroska",
}


@router.get("/documents/{doc_id}/view")
def view_document(doc_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Serves the actual document file (PDF, image, etc.) from disk
    using FileResponse with the appropriate media_type.
    """
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = Path(doc.file_path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found on disk")

    media_type, _ = mimetypes.guess_type(str(file_path))
    if not media_type:
        clean_ext = doc.file_type.lower().lstrip(".") if doc.file_type else ""
        media_type = MIME_TYPE_MAP.get(clean_ext, "application/octet-stream")

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{file_path.name}"'},
    )


@router.get("/documents/{doc_id}/download")
def download_document(doc_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Serves the document file as a forced attachment download.
    """
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = Path(doc.file_path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found on disk")

    media_type, _ = mimetypes.guess_type(str(file_path))
    if not media_type:
        clean_ext = doc.file_type.lower().lstrip(".") if doc.file_type else ""
        media_type = MIME_TYPE_MAP.get(clean_ext, "application/octet-stream")

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=file_path.name,
    )


@router.get("")
def search_documents(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Semantic search across every document's combined text (title, tags,
    description, OCR text, ICR text) using pgvector cosine similarity.

    Works for content that has no OCR/ICR text at all (photos, videos)
    as long as the user supplied a title/tags/description at upload —
    that's the whole point: untaggable-by-OCR content becomes findable
    through whatever text metadata a human did supply.
    """
    query_embedding = compute_embedding(q)

    # pgvector's <=> operator is cosine distance (0 = identical, 2 = opposite).
    # Convert to a similarity score for a more intuitive API response.
    stmt = (
        select(
            Document,
            Document.embedding.cosine_distance(query_embedding).label("distance"),
        )
        .where(Document.embedding.is_not(None))
        .order_by("distance")
        .limit(limit)
    )

    results = db.execute(stmt).all()

    return {
        "query": q,
        "count": len(results),
        "results": [
            {
                "id": str(doc.id),
                "title": doc.title,
                "category": doc.category,
                "collection": doc.collection,
                "file_type": doc.file_type,
                "tags": doc.tags,
                "description": doc.description,
                "similarity": round(1 - distance, 4),  # 1.0 = perfect match
                "ocr_excerpt": (doc.ocr_text or "")[:200] or None,
                "icr_excerpt": (doc.icr_text or "")[:200] or None,
                "ocr_status": doc.ocr_status.value if hasattr(doc.ocr_status, "value") else str(doc.ocr_status or "pending"),
                "icr_status": doc.icr_status.value if hasattr(doc.icr_status, "value") else str(doc.icr_status or "pending"),
                "view_url": f"/search/documents/{doc.id}/view",
                "download_url": f"/search/documents/{doc.id}/download",
            }
            for doc, distance in results
        ],
    }

