import uuid

from fastapi import APIRouter, HTTPException, Depends, Body
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.document import Document
from app.services.metadata_service import extract_metadata

router = APIRouter(prefix="/metadata", tags=["Metadata"])


@router.post("/extract/{document_id}")
def extract_document_metadata(document_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Runs rule-based metadata extraction on whichever text is available for
    this document (prefers OCR text, falls back to ICR text), and stores
    the result on the document's metadata_json column.
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    source_text = document.ocr_text or document.icr_text
    if not source_text:
        raise HTTPException(
            status_code=400,
            detail="No OCR or ICR text available yet for this document. "
                   "Run /ocr/start or /icr/start first.",
        )

    metadata = extract_metadata(source_text)
    document.metadata_json = metadata
    db.commit()
    db.refresh(document)

    return {
        "id": str(document.id),
        "metadata": document.metadata_json,
    }


@router.get("/{document_id}")
def get_document_metadata(document_id: uuid.UUID, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.metadata_json is None:
        raise HTTPException(
            status_code=400,
            detail="No metadata extracted yet. Run POST /metadata/extract/{id} first.",
        )

    return {
        "id": str(document.id),
        "metadata": document.metadata_json,
    }


@router.put("/update/{document_id}")
def update_document_metadata(
    document_id: uuid.UUID,
    updates: dict = Body(..., description="Fields to merge into the existing metadata"),
    db: Session = Depends(get_db),
):
    """
    Lets a human curator correct/override specific fields after automatic
    extraction — e.g. fixing a misread officer name or adding a missing
    battle/operation the rule-based extractor couldn't catch.
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    current = document.metadata_json or {}
    current.update(updates)
    document.metadata_json = current
    db.commit()
    db.refresh(document)

    return {
        "id": str(document.id),
        "metadata": document.metadata_json,
    }
