"""
Chat / RAG endpoint.

Flow:
  1. User sends a question.
  2. We reuse the EXISTING /search logic (pgvector + keyword hybrid search)
     to retrieve the most relevant documents for that question.
  3. We fetch each matched document's FULL ocr/icr text from the database
     and extract a smart ~1500-char excerpt centred on the first query-keyword
     match (instead of relying on the 200-char preview from search.py).
  4. We format those enriched documents into a context block.
  5. We send (context + question) to Groq's LLM.
  6. We return the LLM's answer PLUS the source documents it was grounded in.
"""

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database.session import get_db
from app.api.search import search_documents
from app.models.document_model import Document
from app.services.llm_service import generate_answer

router = APIRouter(prefix="/chat", tags=["Chat"])

# Words that carry no topical meaning — excluded from keyword matching.
_STOPWORDS = {
    "me", "my", "i", "tell", "about", "the", "a", "an", "is", "are", "was",
    "were", "in", "of", "and", "or", "what", "how", "why", "when", "where",
    "who", "which", "this", "that", "it", "its", "to", "for", "on", "at",
    "by", "with", "from", "be", "do", "did", "have", "has", "had", "can",
    "could", "would", "should", "will", "get", "give", "some", "any", "more",
    "all", "just", "also", "but", "not", "so", "up", "if",
}

# Regex tokenizer matching word characters — same approach used in search.py.
_WORD_RE = re.compile(r"\w+", re.UNICODE)

# A source is shown in the UI only if it has a keyword match OR similarity >= this.
_SOURCE_DISPLAY_THRESHOLD = 0.80

# How many characters to extract around the first keyword match.
_EXCERPT_WINDOW = 1500
_EXCERPT_HALF = _EXCERPT_WINDOW // 2   # 750 chars before & after


def _query_terms(text: str) -> list[str]:
    """Meaningful, non-stopword tokens from the query (length > 2)."""
    return [t for t in _WORD_RE.findall(text.lower()) if len(t) > 2 and t not in _STOPWORDS]


def _smart_excerpt(full_text: str, terms: list[str]) -> str:
    """
    Extract a ~1500-char window from *full_text* centred on the first
    occurrence of any term in *terms*.  Falls back to the first 1500
    characters if no keyword is found.
    """
    if not full_text:
        return ""

    text_lower = full_text.lower()
    best_pos: int | None = None

    # Find the earliest occurrence of any meaningful query term.
    for term in terms:
        pos = text_lower.find(term)
        if pos != -1 and (best_pos is None or pos < best_pos):
            best_pos = pos

    if best_pos is not None:
        start = max(0, best_pos - _EXCERPT_HALF)
        end = start + _EXCERPT_WINDOW
        # If we hit the end of the text, shift the window back.
        if end > len(full_text):
            end = len(full_text)
            start = max(0, end - _EXCERPT_WINDOW)
        return full_text[start:end]

    # No keyword match — return the first 1500 characters.
    return full_text[:_EXCERPT_WINDOW]


def _is_displayable_source(doc: dict, terms: list[str]) -> bool:
    """
    Decides whether a doc should appear in the SOURCES panel shown to the user.
    The LLM always gets all retrieved docs for context — this only affects the UI.

    Shows the source if:
      - At least one query term appears in the doc's metadata/text, OR
      - Similarity is high enough (>= 0.80) to be genuinely on-topic.
    """
    doc_text = " ".join(filter(None, [
        doc.get("title", ""),
        doc.get("tags", ""),
        doc.get("description", ""),
        doc.get("ocr_excerpt", ""),
        doc.get("icr_excerpt", ""),
    ])).lower()

    has_keyword = any(t in doc_text for t in terms) if terms else False
    return has_keyword or doc.get("similarity", 0.0) >= _SOURCE_DISPLAY_THRESHOLD


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None   # reserved for future conversation history
    top_k: int = 5                  # how many documents to retrieve as context


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]
    query: str


@router.post("/ask", response_model=ChatResponse)
def ask(request: ChatRequest, db: Session = Depends(get_db)):
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    # Step 1: Retrieve context using the EXISTING search endpoint's function directly.
    search_result = search_documents(q=request.message, limit=request.top_k, db=db)
    retrieved_docs = search_result["results"]

    # Step 2: Enrich each result with a smart ~1500-char excerpt from the FULL
    # ocr/icr text instead of the 200-char preview that search.py returns.
    terms = _query_terms(request.message)

    for doc in retrieved_docs:
        doc_row = db.query(Document).filter(
            Document.id == uuid.UUID(doc["id"])
        ).first()

        if doc_row:
            full_text = (doc_row.ocr_text or "").strip() or (doc_row.icr_text or "").strip()
            if full_text:
                doc["ocr_excerpt"] = _smart_excerpt(full_text, terms)

    # Step 3: Build context and call the LLM (LLM gets ALL retrieved docs).
    try:
        answer_text = generate_answer(request.message, retrieved_docs)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Step 4: Build the sources list for the UI.
    # Only show sources that have a keyword match OR high similarity (>= 0.80).
    # The LLM already has all docs for context — this is purely a UI filter so
    # unrelated files (e.g. a song that is semantically close but off-topic) don't
    # appear as clickable citations next to the answer.
    sources = [
        {
            "id": doc["id"],
            "title": doc["title"],
            "similarity": doc["similarity"],
            "view_url": doc["view_url"],
            "file_type": doc.get("file_type"),  # e.g. "mp4", "mp3", "pdf" — lets the
                                                 # frontend render an inline player for
                                                 # audio/video instead of just a link
        }
        for doc in retrieved_docs
        if _is_displayable_source(doc, terms)
    ]

    return ChatResponse(answer=answer_text, sources=sources, query=request.message)