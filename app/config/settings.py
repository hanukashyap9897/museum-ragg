import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project (museum-rag/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment variables from root .env and app/.env
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / "app" / ".env")


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

    # --- Allowed upload types (documents, images, videos, audio) ---
    ALLOWED_EXTENSIONS: set = {
        ".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif",
        ".mp4", ".webm", ".mov", ".avi", ".mkv",
        ".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma", ".opus"
    }
    MAX_FILE_SIZE_MB: int = 100

    # --- Groq LLM API ---
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


settings = Settings()

# Make sure the uploads folder actually exists on startup
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
