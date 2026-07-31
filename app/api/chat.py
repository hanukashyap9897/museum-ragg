"""
Chat / RAG endpoint.

Flow:
  1. User sends a question.
  2. We reuse the EXISTING /search logic (pgvector + keyword hybrid search)
     to retrieve the most relevant documents for that question.
  3. We format those documents into a context block.
  4. We send (context + question) to Groq's LLM.
  5. We return the LLM's answer PLUS the source documents it was grounded in.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database.session import get_db
from app.api.search import search_documents
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

# A source is shown in the UI only if it has a keyword match OR similarity >= this.
_SOURCE_DISPLAY_THRESHOLD = 0.80


def _query_terms(text: str) -> list[str]:
    """Meaningful, non-stopword tokens from the query (length > 2)."""
    return [t for t in text.lower().split() if len(t) > 2 and t not in _STOPWORDS]


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

    # Step 2 + 3: Build context and call the LLM (LLM gets ALL retrieved docs).
    try:
        answer_text = generate_answer(request.message, retrieved_docs)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Step 4: Build the sources list for the UI.
    # Only show sources that have a keyword match OR high similarity (>= 0.80).
    # The LLM already has all docs for context — this is purely a UI filter so
    # unrelated files (e.g. a song that is semantically close but off-topic) don't
    # appear as clickable citations next to the answer.
    terms = _query_terms(request.message)
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