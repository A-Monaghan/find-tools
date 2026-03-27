"""
API tests — OSINT: health, root, and request validation (no DB).
"""
import pytest


@pytest.mark.asyncio
async def test_root(client):
    r = await client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "FIND Tools API"
    assert "health" in data


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy"
    assert "mode" in data


@pytest.mark.asyncio
async def test_query_empty_rejected(client):
    """OSINT: Empty or missing query must be rejected (422)."""
    r = await client.post("/chat/query", json={"query": ""})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_query_missing_body_rejected(client):
    r = await client.post("/chat/query", json={})
    assert r.status_code == 422
