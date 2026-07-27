"""
Embedding service for semantic search across the museum archive.

Combines every text field a document has — user-supplied title/tags/
description plus any machine-extracted OCR/ICR text — into a single
vector, so a search query can match against whichever piece of content
is actually informative for a given item. A photo with no OCR text still
becomes searchable through its tags/description; a scanned letter with
no tags still becomes searchable through its OCR text.

Uses all-MiniLM-L6-v2: small (~80MB), fast on CPU, 384-dim output.
Good enough for tag/description-level semantic matching — this is not
trying to be a state-of-the-art retrieval model, just "good enough to
find the right museum item by meaning, not just exact keyword match."
"""

from functools import lru_cache

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


def build_document_text(
    title: str | None,
    tags: str | None,
    description: str | None,
    ocr_text: str | None,
    icr_text: str | None,
) -> str:
    """
    Combines every available text field into one blob for embedding.
    Order matters a little (title/tags/description first) since some
    embedding models weight earlier tokens slightly more, and because
    OCR/ICR text can be long and noisy — better that the curated,
    human-supplied fields anchor the meaning of the embedding.
    """
    parts = [title, tags, description, ocr_text, icr_text]
    return "\n".join(p.strip() for p in parts if p and p.strip())


def compute_embedding(text: str) -> list[float]:
    """
    Returns a 384-dim embedding vector for the given text.
    Returns a zero vector if text is empty (avoids a crash on documents
    with literally nothing to embed yet, e.g. mid-upload before OCR runs).
    """
    if not text or not text.strip():
        return [0.0] * 384

    model = _get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def compute_document_embedding(
    title: str | None,
    tags: str | None,
    description: str | None,
    ocr_text: str | None,
    icr_text: str | None,
) -> list[float]:
    """Convenience wrapper: build the combined text, then embed it."""
    text = build_document_text(title, tags, description, ocr_text, icr_text)
    return compute_embedding(text)


def recompute_and_save_embedding(document, db):
    """
    Recomputes a document's embedding from its current title/tags/
    description/ocr_text/icr_text and saves it. Call this any time one
    of those fields changes — most importantly, right after OCR, ICR,
    or IDP processing finishes and populates ocr_text/icr_text, so the
    embedding reflects the newly extracted text instead of only the
    upload-time metadata.
    """
    embedding = compute_document_embedding(
        title=document.title,
        tags=document.tags,
        description=document.description,
        ocr_text=document.ocr_text,
        icr_text=document.icr_text,
    )
    document.embedding = embedding
    db.add(document)
    db.commit()

