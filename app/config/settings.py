import os
from pathlib import Path

# Base directory of the project (museum-rag/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings:
    # --- General ---
    APP_NAME: str = "Assam Regiment Digital Museum API"

    # --- Database (Postgres) ---
    # Update these to match your local Postgres install.
    # Format: postgresql+psycopg2://<user>:<password>@<host>:<port>/<dbname>
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://neondb_owner:npg_VXwv7I6ARFBk@ep-icy-flower-ayaekptz-pooler.c-5.us-east-2.aws.neon.tech/neondb?sslmode=require",
    )

    # --- File storage ---
    UPLOAD_DIR: Path = BASE_DIR / "uploads"

    # --- Allowed upload types (expand later for zip/bulk) ---
    ALLOWED_EXTENSIONS: set = {
        ".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif",
        ".mp4", ".webm", ".mov", ".avi", ".mkv"
    }
    MAX_FILE_SIZE_MB: int = 100

    # --- Groq LLM API ---
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


settings = Settings()

# Make sure the uploads folder actually exists on startup
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
