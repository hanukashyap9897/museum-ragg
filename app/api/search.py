import math
import mimetypes
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, or_

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
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "ogg": "audio/ogg",
    "m4a": "audio/mp4",
}


def _safe_similarity(distance: Optional[float], text_match: bool = False) -> float:
    """
    Safely converts pgvector cosine distance (0 = identical, 2 = opposite)
    to a similarity score (0.0 to 1.0). Handles NaN/Inf values gracefully to
    prevent JSON serialization crashes.
    """
    if distance is None:
        return 0.85 if text_match else 0.0
    try:
        val = float(distance)
        if math.isnan(val) or math.isinf(val):
            return 0.85 if text_match else 0.0
        sim = round(1.0 - val, 4)
        if math.isnan(sim) or math.isinf(sim):
            return 0.85 if text_match else 0.0
        return max(0.0, min(1.0, sim))
    except (ValueError, TypeError):
        return 0.85 if text_match else 0.0


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
    Semantic search across every document's combined text using pgvector
    cosine similarity + text keyword matching fallback.
    """
    query_embedding = compute_embedding(q)

    # 1. Vector Search Query
    stmt_vector = (
        select(
            Document,
            Document.embedding.cosine_distance(query_embedding).label("distance"),
        )
        .where(Document.embedding.is_not(None))
        .order_by("distance")
        .limit(limit)
    )

    results_vector = db.execute(stmt_vector).all()

    # 2. Text Keyword Match Query (fallback for items with pending/zero vectors)
    pattern = f"%{q}%"
    stmt_text = (
        select(Document)
        .where(
            or_(
                Document.title.ilike(pattern),
                Document.tags.ilike(pattern),
                Document.description.ilike(pattern),
                Document.ocr_text.ilike(pattern),
                Document.icr_text.ilike(pattern),
            )
        )
        .limit(limit)
    )
    results_text = db.execute(stmt_text).scalars().all()

    query_terms = [term.strip().lower() for term in q.split() if len(term.strip()) > 1]
    
    seen_ids = set()
    combined_results = []

    # 1. Process Vector Search Results (filter out unrelated items with low similarity and no keyword match)
    for doc, dist in results_vector:
        doc_text = f"{doc.title or ''} {doc.tags or ''} {doc.description or ''} {doc.ocr_text or ''} {doc.icr_text or ''}".lower()
        has_keyword_match = any(term in doc_text for term in query_terms) if query_terms else False
        
        sim = _safe_similarity(dist, text_match=has_keyword_match)
        
        # Boost similarity score if title/tags/description match search terms
        if has_keyword_match and query_terms:
            matched_count = sum(1 for term in query_terms if term in doc_text)
            match_ratio = matched_count / max(1, len(query_terms))
            sim = max(sim, round(0.70 + 0.25 * match_ratio, 4))

        # Filter out completely unrelated items (less than 15% similarity and no keyword match)
        if sim < 0.15 and not has_keyword_match:
            continue

        if str(doc.id) not in seen_ids:
            seen_ids.add(str(doc.id))
            combined_results.append((doc, sim))

    # 2. Process Keyword Fallback Match Results
    for doc in results_text:
        if str(doc.id) not in seen_ids:
            seen_ids.add(str(doc.id))
            doc_text = f"{doc.title or ''} {doc.tags or ''} {doc.description or ''}".lower()
            matched_count = sum(1 for term in query_terms if term in doc_text) if query_terms else 1
            match_ratio = matched_count / max(1, len(query_terms))
            sim = round(0.75 + 0.20 * match_ratio, 4)
            combined_results.append((doc, sim))

    MIN_SIMILARITY_THRESHOLD = 0.35

    # Final filter: strictly exclude irrelevant documents (require >= 35% similarity OR direct keyword match)
    filtered_results = []
    for doc, sim in combined_results:
        doc_text = f"{doc.title or ''} {doc.tags or ''} {doc.description or ''} {doc.ocr_text or ''} {doc.icr_text or ''}".lower()
        has_kw = any(term in doc_text for term in query_terms) if query_terms else False
        
        if has_kw or sim >= MIN_SIMILARITY_THRESHOLD:
            filtered_results.append((doc, sim))

    filtered_results.sort(key=lambda x: x[1], reverse=True)
    final_results = filtered_results[:limit]

    return {
        "query": q,
        "count": len(final_results),
        "results": [
            {
                "id": str(doc.id),
                "title": doc.title,
                "category": doc.category,
                "collection": doc.collection,
                "file_type": doc.file_type,
                "tags": doc.tags,
                "description": doc.description,
                "similarity": sim,
                "ocr_excerpt": (doc.ocr_text or "")[:200] or None,
                "icr_excerpt": (doc.icr_text or "")[:200] or None,
                "ocr_status": doc.ocr_status.value if hasattr(doc.ocr_status, "value") else str(doc.ocr_status or "pending"),
                "icr_status": doc.icr_status.value if hasattr(doc.icr_status, "value") else str(doc.icr_status or "pending"),
                "view_url": f"/search/documents/{doc.id}/view",
                "download_url": f"/search/documents/{doc.id}/download",
            }
            for doc, sim in final_results
        ],
    }


