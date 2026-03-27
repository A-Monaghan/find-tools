"""
Load named chunking presets from JSON (config-driven chunk_size / overlap / strategy).
"""

from dataclasses import dataclass
import json
import logging
from pathlib import Path
from typing import Dict, Optional

from core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChunkPreset:
    """Resolved preset applied to HybridChunker + smart_chunk."""

    id: str
    chunk_size: int
    overlap: int
    strategy: str  # auto | semantic | sections | paragraphs | sliding


_PRESETS_CACHE: Optional[Dict[str, ChunkPreset]] = None


def _presets_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "chunk_presets.json"


def load_presets() -> Dict[str, ChunkPreset]:
    """Load and validate presets from JSON (cached)."""
    global _PRESETS_CACHE
    if _PRESETS_CACHE is not None:
        return _PRESETS_CACHE

    path = _presets_path()
    if not path.is_file():
        settings = get_settings()
        _PRESETS_CACHE = {
            "default": ChunkPreset(
                id="default",
                chunk_size=settings.CHUNK_SIZE,
                overlap=settings.CHUNK_OVERLAP,
                strategy="auto",
            )
        }
        return _PRESETS_CACHE

    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    out: Dict[str, ChunkPreset] = {}
    for key, val in raw.items():
        if not isinstance(val, dict):
            continue
        chunk_size = int(val.get("chunk_size", 512))
        overlap = int(val.get("overlap", 50))
        if chunk_size <= 0:
            logger.warning("Ignoring preset %s: chunk_size must be > 0", key)
            continue
        if overlap < 0:
            logger.warning("Ignoring preset %s: overlap must be >= 0", key)
            continue
        if overlap >= chunk_size:
            logger.warning(
                "Ignoring preset %s: overlap (%s) must be smaller than chunk_size (%s)",
                key,
                overlap,
                chunk_size,
            )
            continue
        out[key] = ChunkPreset(
            id=key,
            chunk_size=chunk_size,
            overlap=overlap,
            strategy=str(val.get("strategy", "auto")),
        )
    if "default" not in out:
        settings = get_settings()
        out["default"] = ChunkPreset(
            id="default",
            chunk_size=settings.CHUNK_SIZE,
            overlap=settings.CHUNK_OVERLAP,
            strategy="auto",
        )
    _PRESETS_CACHE = out
    return _PRESETS_CACHE


def reload_presets() -> None:
    """Clear cache (e.g. after tests)."""
    global _PRESETS_CACHE
    _PRESETS_CACHE = None


def get_chunk_preset(preset_id: Optional[str]) -> ChunkPreset:
    """Resolve preset by id; fall back to default."""
    presets = load_presets()
    pid = (preset_id or "default").strip() or "default"
    if pid in presets:
        return presets[pid]
    return presets["default"]


def list_preset_ids() -> list:
    return sorted(load_presets().keys())
