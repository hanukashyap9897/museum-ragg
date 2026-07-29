"""
One-time data migration: MongoDB Atlas (museum_data collection)
                          -> Neon PostgreSQL (museum_units table)

Run this ONCE after creating the museum_units table (via
scripts/schema_museum_units.sql) and BEFORE switching the frontend
over to the FastAPI CMS routes.

Usage:
    python scripts/migrate_mongo_to_neon.py

Requires MONGODB_URI to still be set (same one Node used) and
DATABASE_URL (Neon) already configured in app/config/settings.py.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pymongo import MongoClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from app.models.museum_unit import MuseumUnit
from app.config.settings import settings


def migrate():
    mongo_uri = os.getenv("MONGODB_URI")
    if not mongo_uri:
        print("[ERROR] MONGODB_URI environment variable is not set.")
        print("        Set it temporarily to your existing Atlas connection string.")
        sys.exit(1)

    print("=" * 70)
    print("     MONGO -> NEON POSTGRES DATA MIGRATION (museum_units)")
    print("=" * 70)

    # --- Connect to MongoDB Atlas ---
    print("\n[1/3] Connecting to MongoDB Atlas...")
    mongo_client = MongoClient(mongo_uri)
    mongo_db = mongo_client["arc_museum"]
    mongo_collection = mongo_db["museum_data"]
    documents = list(mongo_collection.find({}))
    print(f"  [OK] Found {len(documents)} unit document(s) in Mongo.")

    if not documents:
        print("  [INFO] Nothing to migrate. Exiting.")
        return

    # --- Connect to Neon Postgres ---
    print("\n[2/3] Connecting to Neon PostgreSQL...")
    engine = create_engine(settings.DATABASE_URL, echo=False)
    Session = sessionmaker(bind=engine)
    pg_session = Session()
    print("  [OK] Connected.")

    # --- Copy each document over ---
    print("\n[3/3] Migrating documents...")
    migrated = 0
    skipped = 0

    for doc in documents:
        unit_id = doc.get("_id")
        unit_data = doc.get("data")
        updated_at = doc.get("updatedAt", 0)

        if not unit_id or unit_data is None:
            print(f"  [SKIP] Document missing _id or data: {doc}")
            skipped += 1
            continue

        existing = pg_session.query(MuseumUnit).filter(MuseumUnit.id == unit_id).first()
        if existing:
            existing.data = unit_data
            existing.updated_at = updated_at
            print(f"  [UPDATE] {unit_id}")
        else:
            pg_session.add(MuseumUnit(id=unit_id, data=unit_data, updated_at=updated_at))
            print(f"  [INSERT] {unit_id}")

        migrated += 1

    pg_session.commit()
    pg_session.close()
    mongo_client.close()

    print("\n" + "=" * 70)
    print(f"[SUCCESS] Migrated {migrated} unit(s), skipped {skipped}.")
    print("Verify in Neon, then you can safely stop using the Node backend.")
    print("=" * 70)


if __name__ == "__main__":
    migrate()