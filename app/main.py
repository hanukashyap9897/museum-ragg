from contextlib import asynccontextmanager
import threading


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.session import init_db
from app.api import upload, ocr, icr, metadata, signatures, idp, search




def _preload_idp_engine():
    """Load PaddleOCR models once in the background so the first upload isn't blocked."""
    try:
        from app.services.idp_pipeline import _get_engines
        _get_engines()
        print("[startup] IDP engine preloaded")
    except Exception as exc:
        print(f"[startup] IDP preload skipped: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    threading.Thread(target=_preload_idp_engine, daemon=True).start()
    yield


# Create FastAPI application
app = FastAPI(title="Assam Regiment Digital Museum API", lifespan=lifespan)

# CORS — allow the Vite frontend to reach the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Home API
@app.get("/")
def home():
    return {
        "message": "Welcome to Assam Regiment Digital Museum",
        "status": "Backend Running Successfully",
    }


# Wire in the upload endpoints: POST /upload/document, GET /upload/status/{id}
app.include_router(upload.router)

# Wire in the OCR endpoints: POST /ocr/start/{id}, GET /ocr/status/{id}, GET /ocr/result/{id}
app.include_router(ocr.router)

# Wire in the ICR endpoints: POST /icr/start/{id}, GET /icr/status/{id}, GET /icr/result/{id}
app.include_router(icr.router)

# Wire in the Metadata endpoints: POST /metadata/extract/{id}, GET /metadata/{id}, PUT /metadata/update/{id}
app.include_router(metadata.router)

# Wire in the Signature detection endpoint: POST /signatures/detect/{id}
app.include_router(signatures.router)

# Wire in the IDP pipeline endpoints: POST /idp/start/{id}, GET /idp/result/{id}
app.include_router(idp.router)

# Wire in the Search endpoints: GET /search
app.include_router(search.router)

