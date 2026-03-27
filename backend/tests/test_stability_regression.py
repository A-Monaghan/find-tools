"""
Stability regression tests for config/profile and prompt validation.
"""

import pytest


def test_query_request_rejects_invalid_prompt_placeholders():
    """Only {context} is allowed in custom prompt templates."""
    from models.schemas import QueryRequest

    with pytest.raises(ValueError):
        QueryRequest(query="Who is the director?", system_prompt="Use {context} and {foo}")


def test_query_request_requires_context_placeholder():
    """Custom prompts must include {context} to keep RAG deterministic."""
    from models.schemas import QueryRequest

    with pytest.raises(ValueError):
        QueryRequest(query="Summarise", system_prompt="No placeholder here")


def test_stability_profile_safe_applies_expected_flags(monkeypatch):
    """stability_safe enforces low-variance retrieval settings."""
    monkeypatch.setenv("RUNTIME_STABILITY_PROFILE", "stability_safe")
    monkeypatch.setenv("RAG_LOW_LATENCY", "false")
    from core.config import reload_settings

    settings = reload_settings()
    assert settings.RUNTIME_STABILITY_PROFILE == "stability_safe"
    assert settings.ENABLE_HYDE is False
    assert settings.ENABLE_FUSION_RETRIEVAL is False
    assert settings.ENABLE_CORRECTIVE_RAG is False
    assert settings.ENABLE_CROSS_ENCODER_RERANK is False
    assert settings.TOP_K_VECTOR_SEARCH == 12


def test_stability_fingerprint_is_present():
    """Fingerprint should be short and stable-format for incident logs."""
    from core.config import get_settings

    fp = get_settings().stability_fingerprint()
    assert isinstance(fp, str)
    assert len(fp) == 12
    assert fp.isalnum()

