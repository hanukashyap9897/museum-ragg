"""
SQLAlchemy model for the museum_units table — replaces MongoDB's
museum_data collection. Each row = one unit's full CMS content
(meta, history, commandingOfficers, gallery, videos, etc.) stored
as a single JSONB blob, exactly like the old Mongo document shape:

    { "_id": "ARC", "data": {...}, "updatedAt": 1722238739000 }

We keep this as one JSONB column (rather than normalizing into many
tables) because:
  - The frontend already reads/writes this exact nested JSON shape
    (see src/types/index.ts -> UnitData interface).
  - There are only ~5 units (ARC, AR, AS, RR, TA) — not a large dataset
    that needs relational querying/joins.
  - It lets us port the CMS with ZERO frontend changes to data shape.
"""

from sqlalchemy import Column, String, BigInteger
from sqlalchemy.dialects.postgresql import JSONB

from app.models.document_model import Base


class MuseumUnit(Base):
    __tablename__ = "museum_units"

    id = Column(String, primary_key=True)          # e.g. "ARC", "AR", "AS", "RR", "TA"
    data = Column(JSONB, nullable=False)            # full UnitData JSON blob
    updated_at = Column(BigInteger, nullable=False) # epoch milliseconds, matches old Mongo field