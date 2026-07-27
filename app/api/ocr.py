import uuid
import traceback

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from app.database.session import get_db, SessionLocal
from app.models.document import Document, ProcessingStatus
from app.services.ocr_service import run_ocr
from app.services.combined_service import run_combined
from app.services.embedding_service import recompute_and_save_embedding

router = APIRouter(prefix="/ocr", tags=["OCR"])


def _run_ocr_job(document_id: uuid.UUID):
    """
    Runs in the background. Opens its OWN db session because the request's
    session will already be closed by the time this executes.
    """
    db = SessionLocal()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            return

        document.ocr_status = ProcessingStatus.IN_PROGRESS
        db.commit()

        try:
            text = run_ocr(document.file_path, document.file_type)
            document.ocr_text = text
            document.ocr_status = ProcessingStatus.DONE
            db.commit()
            recompute_and_save_embedding(document, db)
        except Exception:
            # Keep the error visible in the terminal for debugging
            print(f"[OCR ERROR] document_id={document_id}\n{traceback.format_exc()}")
            document.ocr_status = ProcessingStatus.FAILED
            db.commit()
    finally:
        db.close()



@router.post("/start/{document_id}")
def start_ocr(document_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.ocr_status == ProcessingStatus.IN_PROGRESS:
        raise HTTPException(status_code=409, detail="OCR already in progress for this document")

    document.ocr_status = ProcessingStatus.PENDING
    db.commit()

    background_tasks.add_task(_run_ocr_job, document_id)

    return {
        "id": str(document_id),
        "ocr_status": "in_progress",
        "message": "OCR started. Poll /ocr/status/{id} for progress.",
    }


@router.get("/status/{document_id}")
def get_ocr_status(document_id: uuid.UUID, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": str(document.id),
        "ocr_status": document.ocr_status,
    }


@router.get("/result/{document_id}")
def get_ocr_result(document_id: uuid.UUID, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.ocr_status == ProcessingStatus.FAILED:
        return {
            "id": str(document.id),
            "status": "failed",
            "error": "OCR processing failed — see server logs for details.",
        }

    if document.ocr_status != ProcessingStatus.DONE:
        return {
            "id": str(document.id),
            "status": "processing",
            "message": "Processing document on server...",
        }

    ocr_text = document.ocr_text or ""
    return {
        "id": str(document.id),
        "status": "completed",
        "ocr_text": ocr_text,
        "result": {
            "clean_text": ocr_text,
            "pages": [
                {
                    "page": 1,
                    "clean_text": ocr_text,
                    "blocks": [
                        {
                            "category": "printed_text",
                            "content": ocr_text,
                        }
                    ],
                }
            ],
        },
    }



def _run_combined_job(document_id: uuid.UUID):
    """
    Same pattern as the plain OCR job, but calls the combined OCR+ICR
    pipeline instead — automatically detects and re-recognizes low-
    confidence (likely handwritten) lines within an otherwise printed page.
    """
    db = SessionLocal()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            return

        document.ocr_status = ProcessingStatus.IN_PROGRESS
        db.commit()

        try:
            text = run_combined(document.file_path, document.file_type)
            document.ocr_text = text
            document.ocr_status = ProcessingStatus.DONE
            db.commit()
            recompute_and_save_embedding(document, db)
        except Exception:
            print(f"[COMBINED OCR+ICR ERROR] document_id={document_id}\n{traceback.format_exc()}")
            document.ocr_status = ProcessingStatus.FAILED
            db.commit()

    finally:
        db.close()


@router.post("/start-combined/{document_id}")
def start_combined_ocr(document_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    For pages that mix printed text AND handwriting (signatures,
    annotations, 'SEEN BY' notes) on the SAME page. Automatically runs
    OCR on the whole page, detects which lines Tesseract is unsure about
    (usually the handwritten parts), and re-recognizes just those lines
    with ICR — no manual region selection needed. Slower than plain OCR
    since it may invoke the ICR model per flagged line.
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.ocr_status == ProcessingStatus.IN_PROGRESS:
        raise HTTPException(status_code=409, detail="Processing already in progress for this document")

    document.ocr_status = ProcessingStatus.PENDING
    db.commit()

    background_tasks.add_task(_run_combined_job, document_id)

    return {
        "id": str(document_id),
        "ocr_status": "in_progress",
        "message": "Combined OCR+ICR started. Poll /ocr/status/{id}, then read "
                   "the merged result from /ocr/result/{id} once done.",
    }
