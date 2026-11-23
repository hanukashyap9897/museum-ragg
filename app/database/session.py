from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config.settings import settings

# ---------------------------------------------------------------------------
# Engine / connection pool
# ---------------------------------------------------------------------------
# pool_pre_ping  – tests each connection with a lightweight "SELECT 1" before
#                  handing it to the caller; discards and replaces dead ones.
# pool_recycle   – force-retires a connection after N seconds so it never sits
#                  idle long enough for the cloud DB (Neon/Supabase) to close
#                  the SSL session on us (their idle timeout is ~300 s).
# pool_size / max_overflow – kept small; long IDP jobs hold a session the whole
#                  time, so fewer concurrent connections is safer than flooding.
engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
    pool_recycle=180,       # well under Neon's 300-s idle-timeout
    pool_size=3,
    max_overflow=5,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# ---------------------------------------------------------------------------
# Request-scoped session dependency
# ---------------------------------------------------------------------------
def get_db():
    """
    FastAPI dependency — yields a DB session per-request.

    The finally block is hardened against the most common failure mode on
    cloud-hosted Postgres (Neon, Supabase, Render …): the server closes the
    SSL connection after a period of idle time, but our pool still holds a
    reference to the now-dead socket.  pool_pre_ping catches this *before*
    handing the connection out, but if the SSL teardown happens *during* a
    long request (e.g. while IDP/OCR is processing), the rollback that
    SQLAlchemy issues at session-close will fail with:

        psycopg2.OperationalError: SSL connection has been closed unexpectedly

    We catch that error, invalidate the broken connection (so SQLAlchemy
    drops it from the pool instead of recycling it), and log a warning
    rather than letting the exception propagate through the whole ASGI stack.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except OperationalError as exc:
            # Dead SSL socket — invalidate the underlying connection so it is
            # removed from the pool, then swallow the error.
            print(
                f"[session] OperationalError on db.close() (stale SSL connection "
                f"discarded from pool): {exc}"
            )
            try:
                db.invalidate()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------
def init_db():
    """
    Creates all tables that don't exist yet.
    Call this once at startup (fine for dev; use Alembic migrations later
    once the schema stabilizes).
    """
    from app.models import document  # noqa: F401  (ensures model is registered)
    Base.metadata.create_all(bind=engine)

