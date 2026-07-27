import uuid
import traceback

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from app.database.session import get_db, SessionLocal
from app.models.document import Document
from app.services.signature_service import detect_and_recognize_signatures

router = APIRouter(prefix="/signatures", tags=["Signatures"])


def _run_signature_job(document_id: uuid.UUID):
    db = SessionLocal()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            return

        try:
            results = detect_and_recognize_signatures(document.file_path, document.file_type)
            existing_metadata = document.metadata_json or {}
            existing_metadata["signatures"] = results
            document.metadata_json = existing_metadata
        except Exception:
            print(f"[SIGNATURE DETECTION ERROR] document_id={document_id}\n{traceback.format_exc()}")

        db.commit()
    finally:
        db.close()


@router.post("/detect/{document_id}")
def start_signature_detection(document_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Finds printed '(Officer Name)' signature-block anchors on each page,
    crops the handwriting zone just above each one, and attempts ICR only
    on zones that actually contain ink (skips blank ones — some copies in
    a bundle use a typed 'Sd/-' placeholder instead of a live signature).

    Does NOT touch the document's main ocr_text — results are stored
    separately under metadata_json["signatures"].
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not document.ocr_text:
        raise HTTPException(
            status_code=400,
            detail="Run /ocr/start on this document first — signature detection "
                   "needs the page images, same as OCR.",
        )

    background_tasks.add_task(_run_signature_job, document_id)

    return {
        "id": str(document_id),
        "message": "Signature detection started. Check GET /metadata/{id} shortly "
                   "for results under the 'signatures' field.",
    }
