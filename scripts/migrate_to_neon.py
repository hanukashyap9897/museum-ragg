import os
import sys
import argparse
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text
from app.models.document_model import Base
from app.config.settings import settings


def migrate_to_neon(target_url: str):
    """
    Connects to Neon Postgres, enables pgvector, creates processingstatus enum,
    and builds all database tables automatically.
    """
    url = target_url.strip()

    # Ensure sslmode=require for Neon PostgreSQL connection if missing
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"

    print("=" * 70)
    print("           NEON POSTGRESQL MIGRATION RUNNER")
    print("=" * 70)
    print(f"Target Database URL: {url.split('@')[-1] if '@' in url else url}")

    try:
        engine = create_engine(url, echo=False)

        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            print("\n[Step 1/3] Enabling 'vector' extension on Neon...")
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            print("  [OK] Extension 'vector' enabled.")

            print("\n[Step 2/3] Creating 'processingstatus' enum type...")
            conn.execute(text("""
                DO $$ 
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'processingstatus') THEN
                        CREATE TYPE processingstatus AS ENUM (
                            'pending',
                            'in_progress',
                            'done',
                            'failed',
                            'skipped',
                            'not_applicable'
                        );
                    END IF;
                END $$;
            """))
            print("  [OK] Enum type 'processingstatus' configured.")

        print("\n[Step 3/3] Building database tables via SQLAlchemy ORM...")
        Base.metadata.create_all(bind=engine)
        print("  [OK] Table 'documents' created successfully.")

        print("\n" + "=" * 70)
        print("[SUCCESS] Neon PostgreSQL Migration Completed Successfully!")
        print("Your Neon database is ready to be used in production.")
        print("=" * 70)

    except Exception as exc:
        print(f"\n[ERROR] Migration failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate Assam Regiment Digital Museum database schema to Neon PostgreSQL."
    )
    parser.add_argument(
        "--url",
        type=str,
        default=os.getenv("DATABASE_URL", settings.DATABASE_URL),
        help="Target Neon PostgreSQL connection string (defaults to DATABASE_URL env var)",
    )
    args = parser.parse_args()

    migrate_to_neon(target_url=args.url)
