import uuid
import traceback
import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.database.session import get_db, SessionLocal
from app.models.document import Document, ProcessingStatus
from app.services.idp_pipeline import run_idp_pipeline
from app.services.embedding_service import recompute_and_save_embedding

router = APIRouter(prefix="/idp", tags=["IDP"])


# ---------------------------------------------------------------------------
# In-memory job status cache
# ---------------------------------------------------------------------------
# Keyed by document_id (str).  Stores the last-known status + progress so
# that GET /idp/result/{id} can answer without touching the database at all
# while the job is in-progress.  The cache entry is written by _run_idp_job
# and by the per-page progress callback, both of which run in the background
# thread — no DB connection required for reads.
#
# Why this matters:
#   The frontend polls /idp/result every few seconds.  Without this cache,
#   every poll grabs a connection from SQLAlchemy's pool.  Combined with the
#   IDP background thread (which holds its own connection for the full job
#   duration) and the per-page progress callback (which was opening a NEW
#   SessionLocal for every page), the pool (size 3 + overflow 5 = 8 max) was
#   exhausted and subsequent polls crashed with QueuePool TimeoutError.
# ---------------------------------------------------------------------------
_job_cache: dict[str, dict[str, Any]] = {}
_job_cache_lock = threading.Lock()


def _cache_set(document_id: str, data: dict):
    with _job_cache_lock:
        _job_cache[document_id] = data


def _cache_get(document_id: str) -> dict | None:
    with _job_cache_lock:
        return _job_cache.get(document_id)


def _cache_delete(document_id: str):
    with _job_cache_lock:
        _job_cache.pop(document_id, None)


# Only one IDP job at a time — PaddleOCR is heavy and not safe to run concurrently
# on CPU; overlapping jobs were reloading models and stalling the server.
_idp_job_lock = threading.Lock()


def _run_idp_job(document_id: uuid.UUID):
    doc_id_str = str(document_id)
    with _idp_job_lock:

        # ------------------------------------------------------------------
        # Phase 1: Read document metadata and mark IN_PROGRESS.
        # Open a DB session, do the work, close it immediately — we must NOT
        # hold a connection open across the IDP pipeline (which takes minutes).
        # Cloud-hosted Postgres (Neon/Supabase) closes idle SSL connections
        # after ~300 s; holding one open through a multi-minute CPU-bound job
        # guarantees it will be dead by the time we try to commit results.
        # ------------------------------------------------------------------
        with SessionLocal() as db:
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                _cache_set(doc_id_str, {"status": "failed", "error": "Document not found"})
                return

            file_path = document.file_path
            file_type = document.file_type
            existing_metadata = dict(document.metadata_json or {})

            document.ocr_status = ProcessingStatus.IN_PROGRESS
            db.commit()

        # Seed cache so the first poll sees "processing" immediately
        _cache_set(doc_id_str, {
            "status": "processing",
            "progress": {"current_page": 0, "total_pages": 0, "percent": 0, "remaining_pages": 0},
        })

        started = datetime.now(timezone.utc).isoformat()
        print(f"[IDP] Job started document_id={document_id} at {started}", flush=True)

        # ------------------------------------------------------------------
        # Progress callback — writes ONLY to the in-memory cache, no DB.
        # ------------------------------------------------------------------
        def _progress_cb(current_page: int, total_pages: int):
            percent = int(((current_page - 0.5) / max(total_pages, 1)) * 90)
            _cache_set(doc_id_str, {
                "status": "processing",
                "progress": {
                    "current_page": current_page,
                    "total_pages": total_pages,
                    "percent": max(10, min(95, percent)),
                    "remaining_pages": max(0, total_pages - current_page + 1),
                },
            })

        # ------------------------------------------------------------------
        # Phase 2: Run IDP pipeline — NO DB connection held at all.
        # If this takes 5+ minutes, that's fine; no connection to time out.
        # ------------------------------------------------------------------
        try:
            result = run_idp_pipeline(file_path, file_type, progress_callback=_progress_cb)
        except Exception:
            print(f"[IDP PIPELINE ERROR] document_id={document_id}\n{traceback.format_exc()}")
            # Phase 2b: Mark FAILED in DB with a fresh connection
            try:
                with SessionLocal() as db:
                    doc = db.query(Document).filter(Document.id == document_id).first()
                    if doc:
                        doc.ocr_status = ProcessingStatus.FAILED
                        db.commit()
            except Exception as db_exc:
                print(f"[IDP] Could not persist FAILED status: {db_exc}", flush=True)
            _cache_set(doc_id_str, {"status": "failed", "error": "IDP processing failed — see server logs."})
            print(f"[IDP] Job failed document_id={document_id}", flush=True)
            return

        # ------------------------------------------------------------------
        # Phase 3: Persist results with a FRESH DB connection.
        # The pipeline is done; we now reconnect briefly just to write.
        # ------------------------------------------------------------------
        total_pages = len(result.get("pages", []))
        progress_final = {
            "current_page": total_pages,
            "total_pages": total_pages,
            "percent": 100,
            "remaining_pages": 0,
        }

        try:
            with SessionLocal() as db:
                doc = db.query(Document).filter(Document.id == document_id).first()
                if doc:
                    new_metadata = dict(existing_metadata)
                    new_metadata["idp_result"] = result
                    new_metadata["progress"] = progress_final
                    doc.metadata_json = new_metadata
                    flag_modified(doc, "metadata_json")
                    doc.ocr_text = result["clean_text"]
                    doc.ocr_status = ProcessingStatus.DONE
                    db.commit()
                    recompute_and_save_embedding(doc, db)

            _cache_set(doc_id_str, {"status": "completed", "progress": progress_final})
            print(f"[IDP] Job completed document_id={document_id}", flush=True)

        except Exception:
            print(f"[IDP] DB write failed after pipeline completed:\n{traceback.format_exc()}")
            _cache_set(doc_id_str, {"status": "failed", "error": "IDP done but DB write failed — see server logs."})



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


# Maps internal ProcessingStatus enum to the exact status strings the frontend expects
_STATUS_MAP = {
    ProcessingStatus.PENDING: "processing",
    ProcessingStatus.IN_PROGRESS: "processing",
    ProcessingStatus.DONE: "completed",
    ProcessingStatus.FAILED: "failed",
}


@router.get("/result/{document_id}")
def get_idp_result(document_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Returns the current status of an IDP job.

    While the job is running, this endpoint answers from the in-memory cache
    — no DB connection consumed.  Only when the status is "completed" or
    "failed" (or the cache is cold, e.g. after a server restart) does it
    fall back to a single DB query to fetch the persisted result.
    """
    doc_id_str = str(document_id)
    cached = _cache_get(doc_id_str)

    # -- Fast path: job is in-progress, serve from memory --
    if cached and cached.get("status") == "processing":
        return {
            "id": doc_id_str,
            "status": "processing",
            "progress": cached.get("progress"),
            "message": "Processing document on server...",
        }

    # -- Fast path: job failed (in memory) --
    if cached and cached.get("status") == "failed":
        return {
            "id": doc_id_str,
            "status": "failed",
            "error": cached.get("error", "IDP processing failed — see server logs."),
        }

    # -- Slow path: completed or cache-miss (server restart) — hit the DB once --
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    status = _STATUS_MAP.get(document.ocr_status, "processing")
    metadata = document.metadata_json or {}
    progress = metadata.get("progress")

    if status == "failed":
        _cache_delete(doc_id_str)
        return {
            "id": doc_id_str,
            "status": "failed",
            "error": "IDP processing failed — see server logs for details.",
        }

    if status != "completed":
        # Cache is cold and job is still running (e.g. just after server restart)
        _cache_set(doc_id_str, {"status": "processing", "progress": progress})
        return {
            "id": doc_id_str,
            "status": "processing",
            "progress": progress,
            "message": "Processing document on server...",
        }

    # Job is done — return result and clean up cache entry
    _cache_delete(doc_id_str)
    return {
        "id": doc_id_str,
        "status": "completed",
        "progress": progress,
        "result": metadata.get("idp_result"),
    }

