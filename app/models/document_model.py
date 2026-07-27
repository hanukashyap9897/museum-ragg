import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Enum, JSON
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from app.database.session import Base


class ProcessingStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
    NOT_APPLICABLE = "not_applicable"


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    category = Column(String, nullable=True)       # e.g. "War Diary", "Photograph"
    collection = Column(String, nullable=True)      # e.g. "Gallantry Awards"
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)      # pdf / png / jpg etc.
    ocr_status = Column(
        Enum(ProcessingStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=ProcessingStatus.PENDING,
    )
    icr_status = Column(
        Enum(ProcessingStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=ProcessingStatus.PENDING,
    )
    ocr_text = Column(String, nullable=True)
    icr_text = Column(String, nullable=True)

    # User-supplied metadata for content that OCR/ICR can't read (photos,
    # videos, or anything the user wants to manually describe/tag).
    tags = Column(String, nullable=True)            # free-text, comma-separated
    description = Column(String, nullable=True)

    # Semantic search vector — built from title + tags + description +
    # ocr_text + icr_text combined. 384 dims matches all-MiniLM-L6-v2.
    embedding = Column(Vector(384), nullable=True)

    # Extracted metadata: year, regiment, operation, officer, place, battle, keywords
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
