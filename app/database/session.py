from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config.settings import settings

# The engine is the actual connection pool to Postgres
engine = create_engine(settings.DATABASE_URL, echo=False, future=True)

# Each request gets its own Session from this factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# All ORM models (Document, etc.) inherit from this
Base = declarative_base()


def get_db():
    """
    FastAPI dependency — yields a DB session per-request and
    always closes it afterwards, even if the request raises.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Creates all tables that don't exist yet.
    Call this once at startup (fine for dev; use Alembic migrations later
    once the schema stabilizes).
    """
    from app.models import document  # noqa: F401  (ensures model is registered)
    Base.metadata.create_all(bind=engine)
