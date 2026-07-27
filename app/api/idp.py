import uuid
import traceback
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.database.session import get_db, SessionLocal
from app.models.document import Document, ProcessingStatus
from app.services.idp_pipeline import run_idp_pipeline
from app.services.embedding_service import recompute_and_save_embedding

router = APIRouter(prefix="/idp", tags=["IDP"])


# Only one IDP job at a time — PaddleOCR is heavy and not safe to run concurrently
# on CPU; overlapping jobs were reloading models and stalling the server.
_idp_job_lock = threading.Lock()


def _run_idp_job(document_id: uuid.UUID):
    with _idp_job_lock:
        db = SessionLocal()
        try:
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                return

            document.ocr_status = ProcessingStatus.IN_PROGRESS
            db.commit()

            started = datetime.now(timezone.utc).isoformat()
            print(f"[IDP] Job started document_id={document_id} at {started}", flush=True)

            def _progress_cb(current_page: int, total_pages: int):
                pdb = SessionLocal()
                try:
                    pdoc = pdb.query(Document).filter(Document.id == document_id).first()
                    if pdoc:
                        meta = dict(pdoc.metadata_json or {})
                        percent = int(((current_page - 0.5) / total_pages) * 90)
                        meta["progress"] = {
                            "current_page": current_page,
                            "total_pages": total_pages,
                            "percent": max(10, min(95, percent)),
                            "remaining_pages": max(0, total_pages - current_page + 1),
                        }
                        pdoc.metadata_json = meta
                        flag_modified(pdoc, "metadata_json")
                        pdb.commit()
                except Exception as exc:
                    print(f"[IDP PROGRESS DB ERROR] {exc}", flush=True)
                finally:
                    pdb.close()

            try:
                result = run_idp_pipeline(document.file_path, document.file_type, progress_callback=_progress_cb)
                existing_metadata = dict(document.metadata_json or {})
                existing_metadata["idp_result"] = result
                existing_metadata["progress"] = {
                    "current_page": len(result.get("pages", [])),
                    "total_pages": len(result.get("pages", [])),
                    "percent": 100,
                    "remaining_pages": 0,
                }
                document.metadata_json = existing_metadata
                flag_modified(document, "metadata_json")
                document.ocr_text = result["clean_text"]
                document.ocr_status = ProcessingStatus.DONE
                db.commit()
                recompute_and_save_embedding(document, db)
                print(f"[IDP] Job completed document_id={document_id}", flush=True)
            except Exception:
                print(f"[IDP PIPELINE ERROR] document_id={document_id}\n{traceback.format_exc()}")
                document.ocr_status = ProcessingStatus.FAILED
                db.commit()
                print(f"[IDP] Job failed document_id={document_id}", flush=True)
        finally:
            db.close()



def _start_idp_job_thread(document_id: uuid.UUID):
    thread = threading.Thread(target=_run_idp_job, args=(document_id,), daemon=True)
    thread.start()


@router.post("/start/{document_id}")
def start_idp(document_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Runs the full IDP pipeline: layout analysis, table HTML reconstruction,
    printed text OCR, and signature-zone flagging (no signature OCR attempt).
    Requires paddleocr installed — this is a heavier dependency than the
    Tesseract-based /ocr/start endpoint.
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.ocr_status == ProcessingStatus.IN_PROGRESS:
        raise HTTPException(status_code=409, detail="Processing already in progress for this document")

    document.ocr_status = ProcessingStatus.PENDING
    db.commit()

    _start_idp_job_thread(document_id)

    return {"id": str(document_id), "status": "processing"}


# Maps internal ProcessingStatus enum to the exact status strings requested:
# processing / completed / failed
_STATUS_MAP = {
    ProcessingStatus.PENDING: "processing",
    ProcessingStatus.IN_PROGRESS: "processing",
    ProcessingStatus.DONE: "completed",
    ProcessingStatus.FAILED: "failed",
}


@router.get("/result/{document_id}")
def get_idp_result(document_id: uuid.UUID, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    status = _STATUS_MAP.get(document.ocr_status, "processing")
    metadata = document.metadata_json or {}
    progress = metadata.get("progress")

    if status == "failed":
        return {
            "id": str(document.id),
            "status": status,
            "error": "IDP processing failed — see server logs for details.",
        }

    if status != "completed":
        return {
            "id": str(document.id),
            "status": status,
            "progress": progress,
            "message": "Processing document on server...",
        }

    idp_result = metadata.get("idp_result")

    return {
        "id": str(document.id),
        "status": status,
        "progress": progress,
        "result": idp_result,
    }
