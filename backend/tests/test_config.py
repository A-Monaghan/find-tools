"""Config loading and defaults (OSINT: operation mode for sensitive vs cloud)."""
import os
import pytest


@pytest.fixture(autouse=True)
def set_test_env():
    os.environ["OPERATION_MODE"] = "hybrid"
    os.environ["VECTOR_STORE_TYPE"] = "qdrant"
    from core.config import reload_settings
    reload_settings()
    yield
    reload_settings()


def test_get_settings_returns_settings():
    from core.config import get_settings
    s = get_settings()
    assert s.OPERATION_MODE in ("private", "hybrid", "cloud")
    assert s.VECTOR_STORE_TYPE in ("qdrant", "pgvector")


def test_upload_dir_path():
    from core.config import get_settings
    s = get_settings()
    assert s.UPLOAD_DIR is not None
    assert "storage" in str(s.UPLOAD_DIR) or "documents" in str(s.UPLOAD_DIR)


def test_citation_threshold_for_grounding():
    from core.config import get_settings
    s = get_settings()
    assert 0 <= s.CITATION_SIMILARITY_THRESHOLD <= 1.0
