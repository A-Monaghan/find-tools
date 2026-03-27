"""
RAG-v2.1 FastAPI Application (product: FIND Tools)

Main entry point for the RAG backend API.
"""

# User-facing API name (OpenAPI + GET /) — repo folder remains RAG-v2.1
API_DISPLAY_NAME = "FIND Tools API"

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.routes import documents, chat, logs, auth, graph, ch, workspaces, screening
from api.dependencies import init_db, close_db
from core.config import get_settings

logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    
    # Ensure upload and CH pipeline directories exist
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    settings.CH_PIPELINE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Initialize database
    await init_db()
    
    logger.info(
        "RAG-v2.1 started mode=%s upload_dir=%s vector_store=%s rate_limit=%s profile=%s config_fingerprint=%s",
        settings.OPERATION_MODE,
        settings.UPLOAD_DIR,
        settings.VECTOR_STORE_TYPE,
        settings.RATE_LIMIT_ENABLED,
        settings.RUNTIME_STABILITY_PROFILE,
        settings.stability_fingerprint(),
    )
    
    yield
    
    # Shutdown
    await close_db()
    logger.info("RAG-v2.1 shutting down")


# Create FastAPI app
app = FastAPI(
    title=API_DISPLAY_NAME,
    description="Retrieval-Augmented Generation API with hybrid local/cloud LLM support",
    version="2.1.0",
    lifespan=lifespan
)

# Add rate limiter
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Handle rate limit exceeded errors."""
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Please slow down.",
            "retry_after": exc.detail
        }
    )


# CORS middleware - use configured origins
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(workspaces.router)
app.include_router(chat.router)
app.include_router(logs.router)
app.include_router(graph.router)
app.include_router(ch.router)
app.include_router(screening.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": API_DISPLAY_NAME,
        "version": "2.1.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
@limiter.exempt
async def health_check(request: Request):
    """Health check endpoint. Returns immediately; provider checks have short timeout."""
    import asyncio
    from services.llm_router import get_llm_router
    
    settings = get_settings()
    try:
        router = get_llm_router()
        providers = await asyncio.wait_for(
            router.get_available_providers(),
            timeout=3.0
        )
    except (asyncio.TimeoutError, Exception) as exc:
        logger.warning("Provider health check failed: %s", exc)
        providers = {}
    neo4j_status = {"connected": False}
    try:
        from api.routes.graph import graph_status
        neo4j_status = await graph_status()
    except Exception as exc:
        logger.warning("Neo4j health check failed: %s", exc)
    return {
        "status": "healthy",
        "mode": settings.OPERATION_MODE,
        "providers": providers,
        "neo4j": neo4j_status,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
