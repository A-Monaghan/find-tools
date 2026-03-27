"""
Pytest fixtures for RAG-v2.1 tests.
OSINT-oriented test data and app client.
"""
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture(scope="session")
def test_env():
    """Minimal env so config loads without real API keys."""
    return {
        "OPERATION_MODE": "cloud",
        "DATABASE_URL": "postgresql+asyncpg://raguser:changeme@localhost/ragdb",
        "VECTOR_STORE_TYPE": "qdrant",
        "QDRANT_URL": "http://localhost:6333",
    }


def _create_test_app():
    """App with no-op lifespan (no DB/vector init) for tests."""
    from api.routes import documents, chat, logs
    from core.config import get_settings

    @asynccontextmanager
    async def test_lifespan(app: FastAPI):
        get_settings().UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        yield

    app = FastAPI(title="FIND Tools API Test", version="2.1.0", lifespan=test_lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    app.include_router(documents.router)
    app.include_router(chat.router)
    app.include_router(logs.router)

    @app.get("/")
    async def root():
        return {"name": "FIND Tools API", "version": "2.1.0", "docs": "/docs", "health": "/health"}

    @app.get("/health")
    async def health_check():
        from core.config import get_settings
        return {"status": "healthy", "mode": get_settings().OPERATION_MODE, "providers": {}}

    return app


@pytest.fixture
def app(test_env):
    """FastAPI app with test env and no DB init."""
    for k, v in test_env.items():
        os.environ[k] = v
    from core.config import reload_settings
    reload_settings()
    return _create_test_app()


@pytest.fixture
async def client(app):
    """Async HTTP client for API tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- OSINT-style test data ---

@pytest.fixture
def osint_source_chunk():
    """Single retrieved chunk simulating an OSINT report excerpt."""
    from services.citation_service import RetrievedChunk
    return RetrievedChunk(
        chunk_id="chunk-1",
        document_id=uuid4(),
        document_name="OSINT_Report_2024_ThreatActor.pdf",
        text="The threat actor designated TA-404 uses infrastructure linked to IP 192.0.2.1 and domains including example-c2.net. Activity was first observed in Q3 2023.",
        start_page=12,
        end_page=12,
        score=0.92,
    )


@pytest.fixture
def osint_source_chunks(osint_source_chunk):
    """Multiple chunks for multi-document OSINT scenario."""
    from services.citation_service import RetrievedChunk
    doc_id = uuid4()
    return [
        osint_source_chunk,
        RetrievedChunk(
            chunk_id="chunk-2",
            document_id=doc_id,
            document_name="OSINT_Report_2024_ThreatActor.pdf",
            text="TA-404 targets financial sector and uses spear-phishing with document macros. IOCs are logged in Appendix B.",
            start_page=14,
            end_page=15,
            score=0.88,
        ),
    ]
