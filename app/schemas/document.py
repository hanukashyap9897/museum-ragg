import uuid
from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, ConfigDict

from app.models.document import ProcessingStatus


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    category: Optional[str] = None
    collection: Optional[str] = None
    file_path: str
    file_type: str
    ocr_status: ProcessingStatus
    icr_status: ProcessingStatus
    tags: Optional[str] = None          # ADD THIS
    description: Optional[str] = None   # ADD THIS
    metadata_json: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class UploadResponse(BaseModel):
    id: uuid.UUID
    title: str
    file_type: str
    status: str
    message: str
