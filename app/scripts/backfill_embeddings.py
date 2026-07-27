"""
One-time backfill: computes embeddings for every existing document that
doesn't have one yet. Needed because documents processed before the
tagging/search feature was added have title/ocr_text/icr_text but no
embedding, so they're invisible to /search (which filters out rows
where embedding IS NULL).

Run once with: python -m app.scripts.backfill_embeddings
"""
from app.database.session import SessionLocal
from app.models.document import Document
from app.services.embedding_service import compute_document_embedding


def backfill():
    db = SessionLocal()
    try:
        documents = db.query(Document).filter(Document.embedding.is_(None)).all()
        print(f"Found {len(documents)} documents with no embedding.")

        updated = 0
        skipped = 0
        for doc in documents:
            embedding = compute_document_embedding(
                title=doc.title,
                tags=doc.tags,
                description=doc.description,
                ocr_text=doc.ocr_text,
                icr_text=doc.icr_text,
            )
            # Skip documents with genuinely nothing to embed (all fields empty)
            if all(v == 0.0 for v in embedding):
                print(f"  SKIP (no text at all): {doc.id} — {doc.title}")
                skipped += 1
                continue

            doc.embedding = embedding
            db.add(doc)
            updated += 1
            print(f"  Embedded: {doc.id} — {doc.title}")

        db.commit()
        print(f"\nDone. Updated {updated} documents, skipped {skipped} with no text.")
    finally:
        db.close()


if __name__ == "__main__":
    backfill()
