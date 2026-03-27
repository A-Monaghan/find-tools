"""
API dependencies for FastAPI.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from core.config import get_settings

# Database engine
_engine = None
_session_maker = None


def get_engine():
    """Get or create database engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            future=True,
            pool_size=10,
            max_overflow=20,
            pool_timeout=30,
            pool_recycle=3600
        )
    return _engine


def get_session_maker():
    """Get or create session maker."""
    global _session_maker
    if _session_maker is None:
        engine = get_engine()
        _session_maker = sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
    return _session_maker


async def get_db() -> AsyncSession:
    """Dependency to get database session."""
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def _db_target_for_errors(database_url: str) -> str:
    """Host:port for logs (no password)."""
    try:
        part = database_url.split("@", 1)[-1]
        return part.split("/", 1)[0]
    except Exception:
        return "(see DATABASE_URL)"



async def ensure_schema_migrations(conn):
    """Add columns introduced after first deploy (Postgres). Idempotent."""
    from sqlalchemy import text
    await conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS workspaces (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
    )
    stmts = [
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS chunk_preset_id VARCHAR(64) DEFAULT 'default'",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS ingest_stage VARCHAR(32)",
        "ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS rag_meta JSONB",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES workspaces(id) ON DELETE SET NULL",
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES workspaces(id) ON DELETE SET NULL",
    ]
    for s in stmts:
        await conn.execute(text(s))
    # Seed one default workspace when empty (investigation case label)
    await conn.execute(
        text(
            """
            INSERT INTO workspaces (id, name)
            SELECT gen_random_uuid(), 'General'
            WHERE NOT EXISTS (SELECT 1 FROM workspaces LIMIT 1)
            """
        )
    )


async def init_db():
    """Initialize database tables."""
    from models.database import Base
    from core.config import env_file_path

    settings = get_settings()
    engine = get_engine()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await ensure_schema_migrations(conn)
    except Exception as e:
        # SQLAlchemy/asyncpg often wrap ConnectionRefusedError
        cur = e
        refused = False
        while cur is not None:
            if isinstance(cur, (ConnectionRefusedError, OSError)) and getattr(
                cur, "errno", None
            ) == 61:
                refused = True
                break
            if "connection refused" in str(cur).lower():
                refused = True
                break
            cur = getattr(cur, "__cause__", None)
        if not refused:
            raise
        target = _db_target_for_errors(settings.DATABASE_URL)
        env_hint = env_file_path()
        raise RuntimeError(
            f"PostgreSQL unreachable at {target}. "
            f"Start: docker compose up -d postgres — then check the port matches DATABASE_URL "
            f"(run: docker port rag-postgres). "
            f"Settings env file: {env_hint}"
        ) from e


async def close_db():
    """Close database connections."""
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None