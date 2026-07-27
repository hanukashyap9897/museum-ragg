import sys
import argparse
from pathlib import Path

# Add project root to sys.path so app modules can be imported when running script directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.session import SessionLocal
from app.models.document import Document


def check_orphaned_files(delete_orphans: bool = False):
    db = SessionLocal()
    try:
        documents = db.query(Document).all()
        total_count = len(documents)

        valid_docs = []
        orphaned_docs = []

        for doc in documents:
            file_path = Path(doc.file_path) if doc.file_path else None
            if file_path and file_path.exists():
                valid_docs.append(doc)
            else:
                orphaned_docs.append(doc)

        print("\n" + "=" * 70)
        print("                ORPHANED FILES DIAGNOSTIC REPORT")
        print("=" * 70)
        print(f"Total documents checked:  {total_count}")
        print(f"Valid documents on disk:  {len(valid_docs)}")
        print(f"Orphaned (missing files): {len(orphaned_docs)}")
        print("=" * 70)

        if orphaned_docs:
            print("\nLIST OF DOCUMENTS WITH MISSING FILES ON DISK:")
            print("-" * 70)
            for i, doc in enumerate(orphaned_docs, 1):
                print(f" {i}. ID:        {doc.id}")
                print(f"    Title:     {doc.title}")
                print(f"    File Path: {doc.file_path}")
                print("-" * 70)
        else:
            print("\n[OK] All document records in the database have valid files on disk!")

        if delete_orphans:
            if not orphaned_docs:
                print("\n[INFO] No orphaned records to delete.")
                return

            print(f"\n⚠️  WARNING: You are about to delete {len(orphaned_docs)} row(s) from PostgreSQL database.")
            confirm = input("Are you sure you want to proceed? (y/N): ").strip().lower()

            if confirm in ("y", "yes"):
                for doc in orphaned_docs:
                    db.delete(doc)
                db.commit()
                print(f"\n[OK] Successfully deleted {len(orphaned_docs)} orphaned document record(s) from PostgreSQL.")
            else:
                print("\n[CANCELLED] Deletion cancelled by user. No records were deleted.")
        else:
            if orphaned_docs:
                print("\n[INFO] Report complete. To delete these missing records, re-run with:")
                print("       python scripts/check_orphaned_files.py --delete-orphans\n")

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Check PostgreSQL documents table for missing files on disk and optionally delete orphaned rows."
    )
    parser.add_argument(
        "--delete-orphans",
        action="store_true",
        help="Delete rows from PostgreSQL whose backing files do not exist on disk.",
    )
    args = parser.parse_args()

    check_orphaned_files(delete_orphans=args.delete_orphans)
