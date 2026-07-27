import uuid
import traceback

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from app.database.session import get_db, SessionLocal
from app.models.document import Document, ProcessingStatus
from app.services.icr_service import run_icr
from app.services.embedding_service import recompute_and_save_embedding

router = APIRouter(prefix="/icr", tags=["ICR"])


def _run_icr_job(document_id: uuid.UUID):
    db = SessionLocal()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            return

        document.icr_status = ProcessingStatus.IN_PROGRESS
        db.commit()

        try:
            text = run_icr(document.file_path, document.file_type)
            document.icr_text = text
            document.icr_status = ProcessingStatus.DONE
            db.commit()
            recompute_and_save_embedding(document, db)
        except Exception:
            print(f"[ICR ERROR] document_id={document_id}\n{traceback.format_exc()}")
            document.icr_status = ProcessingStatus.FAILED
            db.commit()
    finally:
        db.close()



@router.post("/start/{document_id}")
def start_icr(document_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.icr_status == ProcessingStatus.IN_PROGRESS:
        raise HTTPException(status_code=409, detail="ICR already in progress for this document")

    document.icr_status = ProcessingStatus.PENDING
    db.commit()

    background_tasks.add_task(_run_icr_job, document_id)

    return {
        "id": str(document_id),
        "icr_status": "in_progress",
        "message": "ICR started. Poll /icr/status/{id} for progress. "
                   "First run will be slow — downloading the model (~1.3GB).",
    }


@router.get("/status/{document_id}")
def get_icr_status(document_id: uuid.UUID, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": str(document.id),
        "icr_status": document.icr_status,
    }


@router.get("/result/{document_id}")
def get_icr_result(document_id: uuid.UUID, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.icr_status == ProcessingStatus.FAILED:
        return {
            "id": str(document.id),
            "status": "failed",
            "error": "ICR processing failed — see server logs for details.",
        }

    if document.icr_status != ProcessingStatus.DONE:
        return {
            "id": str(document.id),
            "status": "processing",
            "message": "Processing handwritten document on server...",
        }

    icr_text = document.icr_text or ""
    return {
        "id": str(document.id),
        "status": "completed",
        "icr_text": icr_text,
        "result": {
            "clean_text": icr_text,
            "pages": [
                {
                    "page": 1,
                    "clean_text": icr_text,
                    "blocks": [
                        {
                            "category": "handwritten_text",
                            "content": icr_text,
                        }
                    ],
                }
            ],
        },
    }

