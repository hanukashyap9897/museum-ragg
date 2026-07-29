"""
CMS API — FastAPI replacement for the old Node/Express + MongoDB backend
(frontend/server/server.js and frontend/api/*.ts).

Every endpoint below has the SAME path, method, request shape, and
response shape as the original Node routes, so the frontend needs
ZERO changes to its data-fetching code — only its base URL changes.

Old Node route          -> New FastAPI route (same path/method/response)
GET  /api/get-all-data  -> GET  /api/get-all-data
POST /api/save-data     -> POST /api/save-data
POST /api/reset-data    -> POST /api/reset-data
POST /api/upload-image  -> POST /api/upload-image
POST /api/upload-video  -> POST /api/upload-video
POST /api/upload-audio  -> POST /api/upload-audio
"""

import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database.session import get_db
from app.models.museum_unit import MuseumUnit

router = APIRouter(prefix="/api", tags=["CMS"])

# ── Static file storage (mirrors old public/images, public/videos, public/audio) ──
# IMPORTANT: point at frontend/public — the SAME physical folder the old
# Node server used (server.js resolved '../public/images' relative to
# frontend/server/). Existing gallery/video URLs already reference files
# stored here, so we must keep using this exact location, not a new folder.
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # museum-rag/
FRONTEND_PUBLIC_DIR = BASE_DIR / "frontend" / "public"
IMAGES_DIR = FRONTEND_PUBLIC_DIR / "images"
VIDEOS_DIR = FRONTEND_PUBLIC_DIR / "videos"
AUDIO_DIR = FRONTEND_PUBLIC_DIR / "audio"

for d in (IMAGES_DIR, VIDEOS_DIR, AUDIO_DIR):
    d.mkdir(parents=True, exist_ok=True)


def _sanitize_filename(original_name: str) -> str:
    """Same sanitization logic as the old multer filename function:
    strips extension, replaces non-alphanumeric chars, appends timestamp."""
    stem = Path(original_name).stem
    ext = Path(original_name).suffix
    safe_stem = "".join(c if c.isalnum() else "_" for c in stem)
    return f"{safe_stem}_{int(time.time() * 1000)}{ext}"


async def _save_upload(file: UploadFile, dest_dir: Path, url_prefix: str) -> dict:
    if not file:
        raise HTTPException(status_code=400, detail=f"No file provided")

    filename = _sanitize_filename(file.filename or "upload")
    dest_path = dest_dir / filename

    # 200MB limit, same as old multer config
    MAX_SIZE = 200 * 1024 * 1024
    contents = await file.read()
    if len(contents) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds 200MB limit")

    with open(dest_path, "wb") as f:
        f.write(contents)

    return {"success": True, "url": f"/{url_prefix}/{filename}"}


# ── GET /api/get-all-data ──
@router.get("/get-all-data")
def get_all_data(db: Session = Depends(get_db)):
    """Returns { success: true, data: { [unit_id]: unitDataObj } } — same shape as before."""
    units = db.query(MuseumUnit).all()
    data_map = {unit.id: unit.data for unit in units}
    return {"success": True, "data": data_map}


# ── POST /api/save-data ──
class SaveDataRequest(BaseModel):
    id: str
    data: Any


@router.post("/save-data")
def save_data(request: SaveDataRequest, db: Session = Depends(get_db)):
    """Upserts a unit's data by id — same behavior as Mongo's updateOne(..., upsert=True)."""
    if not request.id:
        raise HTTPException(status_code=400, detail="Document ID is required")

    now_ms = int(time.time() * 1000)
    existing = db.query(MuseumUnit).filter(MuseumUnit.id == request.id).first()

    if existing:
        existing.data = request.data
        existing.updated_at = now_ms
    else:
        db.add(MuseumUnit(id=request.id, data=request.data, updated_at=now_ms))

    db.commit()
    return {"success": True}


# ── POST /api/reset-data ──
class ResetDataRequest(BaseModel):
    id: Optional[str] = None
    all: Optional[bool] = False


@router.post("/reset-data")
def reset_data(request: ResetDataRequest, db: Session = Depends(get_db)):
    if request.all:
        db.query(MuseumUnit).delete()
        db.commit()
        return {"success": True, "message": "All data database reset"}

    if not request.id:
        raise HTTPException(status_code=400, detail="Document ID or all flag is required")

    db.query(MuseumUnit).filter(MuseumUnit.id == request.id).delete()
    db.commit()
    return {"success": True, "message": f"Document {request.id} reset"}


# ── POST /api/upload-image ──
@router.post("/upload-image")
async def upload_image(image: UploadFile = File(...)):
    return await _save_upload(image, IMAGES_DIR, "images")


# ── POST /api/upload-video ──
@router.post("/upload-video")
async def upload_video(video: UploadFile = File(...)):
    return await _save_upload(video, VIDEOS_DIR, "videos")


# ── POST /api/upload-audio ──
@router.post("/upload-audio")
async def upload_audio(audio: UploadFile = File(...)):
    return await _save_upload(audio, AUDIO_DIR, "audio")