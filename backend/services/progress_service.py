"""
Progress reporting for document ingestion.
Stores stage updates in Redis for SSE streaming to the frontend.
"""

import json
import logging
from typing import Optional
from uuid import UUID

from core.config import get_settings

logger = logging.getLogger(__name__)

PROGRESS_KEY_PREFIX = "doc:"
PROGRESS_TTL = 3600  # 1 hour


def _get_redis():
    """Get Redis client. Returns None if Redis unavailable."""
    try:
        import redis
        settings = get_settings()
        return redis.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception as e:
        logger.warning("Redis unavailable for progress: %s", e)
        return None


def set_progress(document_id: UUID, stage: str, progress: int = 0, message: str = "", batch_n: Optional[int] = None, batch_m: Optional[int] = None):
    """Store progress for a document. Stage: parsing, chunking, embedding, storing, indexed, error."""
    r = _get_redis()
    if not r:
        return
    key = f"{PROGRESS_KEY_PREFIX}{document_id}:progress"
    data = {"stage": stage, "progress": progress, "message": message}
    if batch_n is not None:
        data["batch_n"] = batch_n
    if batch_m is not None:
        data["batch_m"] = batch_m
    try:
        r.setex(key, PROGRESS_TTL, json.dumps(data))
    except Exception as e:
        logger.warning("Failed to set progress: %s", e)


def get_progress(document_id: UUID) -> Optional[dict]:
    """Get current progress for a document."""
    r = _get_redis()
    if not r:
        return None
    key = f"{PROGRESS_KEY_PREFIX}{document_id}:progress"
    try:
        raw = r.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def clear_progress(document_id: UUID):
    """Remove progress key after completion."""
    r = _get_redis()
    if not r:
        return
    key = f"{PROGRESS_KEY_PREFIX}{document_id}:progress"
    try:
        r.delete(key)
    except Exception:
        pass
