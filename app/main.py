import os
from contextlib import asynccontextmanager
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.session import init_db
from app.api import upload, ocr, icr, metadata, signatures, idp, search, cms, chat


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

# CORS — allow Vite frontend (local & deployed on Render) to reach the API
allowed_origins_env = os.getenv("ALLOWED_ORIGINS")
origins = [origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()] if allowed_origins_env else [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    "https://museum-ai-2-0-1.onrender.com",
    "https://museum-ai-2-0-1-rag.onrender.com",
    "https://museum-ai-2-0-1-node.onrender.com",
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=600,
)


@app.options("/{full_path:path}")
async def options_handler(full_path: str):
    return {}


# Home API & Render Health Check Endpoint
@app.api_route("/", methods=["GET", "HEAD"])
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

# Wire in the Chat / RAG endpoints: POST /chat/ask
app.include_router(chat.router)

# Wire in the CMS endpoints: GET /api/get-all-data, POST /api/save-data,
# POST /api/reset-data, POST /api/upload-image, POST /api/upload-video, POST /api/upload-audio
app.include_router(cms.router)

# Serve uploaded media files (replaces Node's express.static for /images, /videos, /audio)
from fastapi.staticfiles import StaticFiles
from app.api.cms import IMAGES_DIR, VIDEOS_DIR, AUDIO_DIR

app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")
app.mount("/videos", StaticFiles(directory=str(VIDEOS_DIR)), name="videos")
app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio")