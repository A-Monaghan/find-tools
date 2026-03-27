"""
Standalone Companies House API — minimal FastAPI app with only CH pipeline.
Use when full RAG install fails (unstructured, pikepdf, etc.).

  cd backend && pip install -r requirements-ch-minimal.txt
  uvicorn ch_standalone:app --host 0.0.0.0 --port 8010

Frontend: point VITE_API_BASE_URL to http://localhost:8010 or proxy /api to 8010.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.ch import router as ch_router
from core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    from api.routes.ch import _cleanup_expired_jobs
    settings = get_settings()
    settings.CH_PIPELINE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if settings.CH_JOB_EXPIRY_HOURS > 0:
        _cleanup_expired_jobs(settings.CH_PIPELINE_OUTPUT_DIR, settings.CH_JOB_EXPIRY_HOURS)
    print("✓ CH standalone started")
    yield
    print("✓ CH standalone shutting down")


app = FastAPI(
    title="CH Pipeline API",
    description="Companies House data fetch and Neo4j export",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ch_router)


@app.get("/")
async def root():
    return {"name": "CH Pipeline API", "version": "1.0.0", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
