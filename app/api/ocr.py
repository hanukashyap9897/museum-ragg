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

    The long OCR work can exceed Neon's ~300 s idle-SSL timeout, so we use
    the same 3-phase pattern as _run_combined_job: mark IN_PROGRESS, close
    the session, do the heavy work, then open a fresh session to write back.
    """
    # ── Phase 1: mark as IN_PROGRESS ────────────────────────────────────────
    db = SessionLocal()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            return
        file_path = document.file_path
        file_type = document.file_type
        document.ocr_status = ProcessingStatus.IN_PROGRESS
        db.commit()
    finally:
        db.close()

    # ── Phase 2: heavy OCR work (no DB session held) ─────────────────────────
    ocr_text: str | None = None
    ocr_error: str | None = None
    try:
        ocr_text = run_ocr(file_path, file_type)
    except Exception:
        ocr_error = traceback.format_exc()
        print(f"[OCR ERROR] document_id={document_id}\n{ocr_error}")

    # ── Phase 3: write result with a fresh session ───────────────────────────
    db2 = SessionLocal()
    try:
        document = db2.query(Document).filter(Document.id == document_id).first()
        if not document:
            return
        if ocr_error:
            document.ocr_status = ProcessingStatus.FAILED
        else:
            document.ocr_text = ocr_text
            document.ocr_status = ProcessingStatus.DONE
        db2.commit()
        if not ocr_error:
            recompute_and_save_embedding(document, db2)
    except Exception:
        print(f"[OCR WRITE-BACK ERROR] document_id={document_id}\n{traceback.format_exc()}")
        try:
            db2.rollback()
        except Exception:
            pass
        db3 = SessionLocal()
        try:
            doc = db3.query(Document).filter(Document.id == document_id).first()
            if doc:
                doc.ocr_status = ProcessingStatus.FAILED
                db3.commit()
        except Exception:
            pass
        finally:
            db3.close()
    finally:
        db2.close()



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
    Same pattern as _run_ocr_job. Uses the 3-phase session approach so the
    long run_combined() call does not hold an SSL connection open past Neon's
    ~300 s idle timeout.
    """
    # ── Phase 1: mark as IN_PROGRESS ────────────────────────────────────────
    db = SessionLocal()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            return
        file_path = document.file_path
        file_type = document.file_type
        document.ocr_status = ProcessingStatus.IN_PROGRESS
        db.commit()
    finally:
        db.close()

    # ── Phase 2: heavy OCR+ICR work (no DB session held) ─────────────────────
    ocr_text: str | None = None
    ocr_error: str | None = None
    try:
        ocr_text = run_combined(file_path, file_type)
    except Exception:
        ocr_error = traceback.format_exc()
        print(f"[COMBINED OCR+ICR ERROR] document_id={document_id}\n{ocr_error}")

    # ── Phase 3: write result with a *fresh* session ─────────────────────────
    db2 = SessionLocal()
    try:
        document = db2.query(Document).filter(Document.id == document_id).first()
        if not document:
            return
        if ocr_error:
            document.ocr_status = ProcessingStatus.FAILED
        else:
            document.ocr_text = ocr_text
            document.ocr_status = ProcessingStatus.DONE
        db2.commit()
        if not ocr_error:
            recompute_and_save_embedding(document, db2)
    except Exception:
        print(f"[COMBINED WRITE-BACK ERROR] document_id={document_id}\n{traceback.format_exc()}")
        try:
            db2.rollback()
        except Exception:
            pass
        db3 = SessionLocal()
        try:
            doc = db3.query(Document).filter(Document.id == document_id).first()
            if doc:
                doc.ocr_status = ProcessingStatus.FAILED
                db3.commit()
        except Exception:
            pass
        finally:
            db3.close()
    finally:
        db2.close()


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
