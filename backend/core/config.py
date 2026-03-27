"""
Configuration management for RAG-v2.1.
Supports hybrid local/cloud operation modes for privacy flexibility.
"""

from pathlib import Path
import hashlib
from typing import Optional, List
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root (RAG-v2.1/) — same regardless of cwd when running uvicorn from backend/ or scripts/
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Load from `.env` at repo root; ignore keys only used by Docker Compose."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.is_file() else None,
        env_file_encoding="utf-8",
        extra="ignore",  # e.g. PORT, ENTITY_EXTRACTOR_URL — not consumed by the FastAPI app
    )
    
    # === OPERATION MODE ===
    # "private" = local only (vLLM + local embeddings; requires ENABLE_VLLM)
    # "hybrid" = prefer local, fallback to cloud (vLLM only if ENABLE_VLLM)
    # "cloud" = cloud only (OpenRouter + OpenAI embeddings) — default for hosted deploy
    OPERATION_MODE: str = Field(default="cloud", description="System operation mode")
    
    # === SECURITY ===
    SECRET_KEY: str = Field(default="changeme-in-dev", description="Secret key for JWT")
    ALGORITHM: str = Field(default="HS256", description="JWT algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, description="Token expiry")
    
    # CORS - comma-separated list of allowed origins
    CORS_ORIGINS: str = Field(default="http://localhost:3000", description="Allowed CORS origins")
    
    # Rate limiting
    RATE_LIMIT_ENABLED: bool = Field(default=True, description="Enable rate limiting")
    RATE_LIMIT_PER_MINUTE: int = Field(default=60, description="Requests per minute")
    
    # === DATABASE ===
    # Also in .env.example for docker-compose substitution (same password must match DATABASE_URL)
    DB_PASSWORD: Optional[str] = Field(default=None, description="Postgres password (compose / docs)")
    DATABASE_URL: str = Field(
        # Match docker-compose default DB_PASSWORD=changeme
        default="postgresql+asyncpg://raguser:changeme@127.0.0.1:5432/ragdb",
        description="PostgreSQL connection string (use 127.0.0.1 when API runs on host, not `postgres`)",
    )
    
    # === REDIS ===
    REDIS_URL: str = Field(default="redis://localhost:6379", description="Redis URL for caching")
    
    # === VECTOR STORE ===
    VECTOR_STORE_TYPE: str = Field(default="qdrant", description="qdrant or pgvector")
    QDRANT_URL: str = Field(default="http://localhost:6333", description="Qdrant server URL")
    QDRANT_COLLECTION: str = Field(default="document_chunks", description="Qdrant collection name")
    
    # === EMBEDDINGS ===
    LOCAL_EMBED_MODEL: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="Local embedding model"
    )
    EMBEDDING_DIMENSION: int = Field(default=384, description="Embedding vector dimension")
    
    # Cloud embeddings (optional)
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API key for cloud embeddings")
    CLOUD_EMBED_MODEL: str = Field(default="text-embedding-3-small", description="Cloud embedding model")
    
    # === CHUNKING ===
    CHUNK_SIZE: int = Field(default=512, description="Token size per chunk")
    CHUNK_OVERLAP: int = Field(default=50, description="Token overlap between chunks")
    
    # === RETRIEVAL ===
    TOP_K_VECTOR_SEARCH: int = Field(default=20, description="Number of chunks from vector search")
    TOP_K_RERANK: int = Field(default=5, description="Number of chunks after reranking")
    
    # === LOCAL LLM (vLLM) — opt-in; off by default for cloud deployments ===
    ENABLE_VLLM: bool = Field(default=False, description="Register vLLM provider (private/hybrid)")
    VLLM_URL: str = Field(default="http://localhost:8000/v1", description="vLLM server URL")
    VLLM_MODEL: Optional[str] = Field(default=None, description="vLLM model name (auto-detected if None)")
    
    # === CLOUD LLM (OpenRouter) ===
    OPENROUTER_API_KEY: Optional[str] = Field(default=None, description="OpenRouter API key")
    DEFAULT_CLOUD_MODEL: str = Field(
        default="moonshotai/kimi-k2.5",
        description="Default cloud LLM model"
    )
    # Mini / cheap model for quick iterations (OpenRouter id); must match a model your key can call
    OPENROUTER_FAST_MODEL: str = Field(
        default="openai/gpt-4o-mini",
        description="Fast, low-cost OpenRouter model for draft passes in the UI",
    )
    LLM_TEMPERATURE: float = Field(default=0.1, description="LLM temperature")
    LLM_MAX_TOKENS: int = Field(default=2000, description="Max tokens for LLM response")
    
    # === STORAGE ===
    UPLOAD_DIR: Path = Field(default=Path("./storage/documents"), description="PDF upload directory")
    MAX_FILE_SIZE_MB: int = Field(default=500, description="Maximum file size in MB")
    
    # === CITATION ===
    CITATION_SIMILARITY_THRESHOLD: float = Field(
        default=0.85,
        description="Minimum similarity for citation validation"
    )

    # === ADVANCED RAG ===
    ENABLE_DOCLING: bool = Field(default=True, description="Use Docling for multi-format parsing")
    CHUNKING_STRATEGY: str = Field(default="auto", description="Chunking strategy")
    ENABLE_FUSION_RETRIEVAL: bool = Field(default=True, description="BM25 + dense fusion")
    FUSION_ALPHA: float = Field(default=0.5, description="Dense vs BM25 weight")
    ENABLE_HYDE: bool = Field(default=True, description="HyDE for short queries")
    HYDE_MIN_WORDS: int = Field(default=8, description="Use HyDE when query has fewer words")
    HYDE_USE_FOR_QUESTIONS: bool = Field(default=True, description="Use HyDE for questions (query ends with ?)")
    ENABLE_CORRECTIVE_RAG: bool = Field(default=True, description="Self-check retrieval + web fallback")
    # Cross-encoder rerank (sentence-transformers) — accurate but slow on CPU; turn off for snappier chat
    ENABLE_CROSS_ENCODER_RERANK: bool = Field(
        default=True,
        description="Re-rank vector hits with ms-marco cross-encoder (disable for lower latency)",
    )
    # When true, forces HyDE, fusion, CRAG, and cross-encoder rerank off (fastest path; quality may drop)
    RAG_LOW_LATENCY: bool = Field(default=False, description="Enable fast chat preset (overrides several RAG flags)")
    RUNTIME_STABILITY_PROFILE: str = Field(
        default="custom",
        description="Runtime profile: custom | stability_safe | stability_full",
    )

    # === NEO4J GRAPH ===
    NEO4J_URI: str = Field(default="bolt://localhost:7687", description="Neo4j Bolt URI")
    NEO4J_USERNAME: str = Field(default="neo4j", description="Neo4j username")
    NEO4J_PASSWORD: str = Field(default="changeme", description="Neo4j password")
    NEO4J_VECTOR_INDEX: str = Field(default="chunk_embeddings", description="Neo4j vector index name")
    ENABLE_GRAPH_INGEST: bool = Field(
        default=False,
        description="Auto-build knowledge graph on document ingest"
    )
    GRAPH_EXTRACTION_MODEL: str = Field(
        default="openai/gpt-4o-mini",
        description="LLM model for entity extraction (OpenRouter ID or vllm/local)"
    )

    # === COMPANIES HOUSE ===
    COMPANIES_HOUSE_API_KEY: Optional[str] = Field(
        default=None,
        description="Companies House API key (optional; can be provided in UI)"
    )
    CH_PIPELINE_OUTPUT_DIR: Path = Field(
        default=Path("./storage/ch_pipeline"),
        description="Output directory for CH pipeline CSVs"
    )
    CH_JOB_EXPIRY_HOURS: int = Field(
        default=0,
        description="Hours before job outputs are auto-deleted (0 = never, manual delete only)"
    )

    # === SCREENING (OpenSanctions / Aleph / Sayari) — server-side keys only ===
    OPENSANCTIONS_API_KEY: Optional[str] = Field(
        default=None,
        description="OpenSanctions hosted match API (https://api.opensanctions.org/match/...)",
    )
    ALEPH_API_KEY: Optional[str] = Field(
        default=None,
        description="OCCRP Aleph API key (entities search)",
    )
    ALEPH_API_BASE: Optional[str] = Field(
        default=None,
        description="Override Aleph API base (default https://aleph.occrp.org/api/2)",
    )
    SAYARI_CLIENT_ID: Optional[str] = Field(default=None, description="Sayari OAuth client id")
    SAYARI_CLIENT_SECRET: Optional[str] = Field(
        default=None,
        description="Sayari OAuth client secret",
    )
    SAYARI_API_BASE: Optional[str] = Field(
        default=None,
        description="Override Sayari API base (default https://api.sayari.com)",
    )

    # === LOGGING ===
    LOG_LEVEL: str = Field(default="INFO", description="Log level")

    @model_validator(mode="after")
    def docker_service_names_to_localhost(self):
        """Compose uses hostnames like `postgres`; they only resolve inside the Docker network."""
        updates = {}
        url = self.DATABASE_URL
        if "@postgres:" in url:
            updates["DATABASE_URL"] = url.replace("@postgres:", "@127.0.0.1:", 1)
        elif "@postgres/" in url:
            updates["DATABASE_URL"] = url.replace("@postgres/", "@127.0.0.1:5432/", 1)
        q = self.QDRANT_URL
        if q.startswith("http://qdrant:") or q.startswith("https://qdrant:"):
            updates["QDRANT_URL"] = q.replace("qdrant", "127.0.0.1", 1)
        r = self.REDIS_URL
        if r.startswith("redis://redis:") or r.startswith("redis://redis/"):
            updates["REDIS_URL"] = r.replace("redis://redis", "redis://127.0.0.1", 1)

        return self.model_copy(update=updates) if updates else self

    @model_validator(mode="after")
    def validate_stability_and_chunking(self):
        """Fail early on invalid runtime combinations that cause flaky behaviour."""
        if self.CHUNK_SIZE <= 0:
            raise ValueError("CHUNK_SIZE must be > 0")
        if self.CHUNK_OVERLAP < 0:
            raise ValueError("CHUNK_OVERLAP must be >= 0")
        if self.CHUNK_OVERLAP >= self.CHUNK_SIZE:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        if self.RUNTIME_STABILITY_PROFILE not in {"custom", "stability_safe", "stability_full"}:
            raise ValueError("RUNTIME_STABILITY_PROFILE must be custom, stability_safe, or stability_full")
        return self

    def get_cors_origins(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    def stability_fingerprint(self) -> str:
        """Short deterministic signature for incident reproduction."""
        key_values = [
            self.OPERATION_MODE,
            self.RUNTIME_STABILITY_PROFILE,
            str(self.ENABLE_HYDE),
            str(self.ENABLE_FUSION_RETRIEVAL),
            str(self.ENABLE_CORRECTIVE_RAG),
            str(self.ENABLE_CROSS_ENCODER_RERANK),
            str(self.TOP_K_VECTOR_SEARCH),
            str(self.TOP_K_RERANK),
            str(self.CHUNK_SIZE),
            str(self.CHUNK_OVERLAP),
            self.DEFAULT_CLOUD_MODEL,
            self.OPENROUTER_FAST_MODEL,
            self.LOCAL_EMBED_MODEL,
            self.CLOUD_EMBED_MODEL,
        ]
        return hashlib.sha1("|".join(key_values).encode("utf-8")).hexdigest()[:12]


# Global settings instance
_settings: Optional[Settings] = None


def _apply_rag_low_latency(s: Settings) -> Settings:
    """When RAG_LOW_LATENCY is set, skip HyDE, fusion, CRAG, and cross-encoder rerank (faster turns)."""
    if not s.RAG_LOW_LATENCY:
        return s
    return s.model_copy(
        update={
            "ENABLE_HYDE": False,
            "ENABLE_FUSION_RETRIEVAL": False,
            "ENABLE_CORRECTIVE_RAG": False,
            "ENABLE_CROSS_ENCODER_RERANK": False,
        }
    )


def _apply_stability_profile(s: Settings) -> Settings:
    """Apply known-good profile defaults for repeatable stability runs."""
    if s.RUNTIME_STABILITY_PROFILE == "stability_safe":
        return s.model_copy(
            update={
                "RAG_LOW_LATENCY": False,
                "ENABLE_HYDE": False,
                "ENABLE_FUSION_RETRIEVAL": False,
                "ENABLE_CORRECTIVE_RAG": False,
                "ENABLE_CROSS_ENCODER_RERANK": False,
                "TOP_K_VECTOR_SEARCH": 12,
                "TOP_K_RERANK": 5,
            }
        )
    if s.RUNTIME_STABILITY_PROFILE == "stability_full":
        return s.model_copy(
            update={
                "RAG_LOW_LATENCY": False,
                "ENABLE_HYDE": True,
                "ENABLE_FUSION_RETRIEVAL": True,
                "ENABLE_CORRECTIVE_RAG": True,
                "ENABLE_CROSS_ENCODER_RERANK": True,
                "TOP_K_VECTOR_SEARCH": 20,
                "TOP_K_RERANK": 5,
            }
        )
    return s


def get_settings() -> Settings:
    """Get or create settings singleton."""
    global _settings
    if _settings is None:
        _settings = _apply_rag_low_latency(_apply_stability_profile(Settings()))
    return _settings


def reload_settings() -> Settings:
    """Reload settings from environment (useful for testing)."""
    global _settings
    _settings = _apply_rag_low_latency(_apply_stability_profile(Settings()))
    return _settings


def repo_root() -> Path:
    """Project root (parent of `backend/`)."""
    return _REPO_ROOT


def env_file_path() -> Path:
    """Path to `.env` used for settings (may or may not exist)."""
    return _ENV_FILE
