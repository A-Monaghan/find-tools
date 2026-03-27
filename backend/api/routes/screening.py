"""
Name + DOB screening across OpenSanctions (hosted match / FTM-backed index), Aleph, Sayari.

Keys are read server-side from env — never expose secrets to the browser.
"""

from __future__ import annotations

import difflib
import hashlib
import logging
import time
from typing import Any, Literal

import requests
from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/screening", tags=["screening"])

OPENSANCTIONS_MATCH_BASE = "https://api.opensanctions.org/match"
DEFAULT_ALEPH_API = "https://aleph.occrp.org/api/2"
DEFAULT_SAYARI_API = "https://api.sayari.com"

# Sayari OAuth tokens keyed by credential set (per-client cache, ~50m)
_sayari_token_cache: dict[str, tuple[str, float]] = {}


def _fuzzy_ratio(a: str, b: str) -> float:
    """Lightweight name similarity for ranking (stdlib only)."""
    a, b = (a or "").strip().lower(), (b or "").strip().lower()
    if not a or not b:
        return 0.0
    return round(difflib.SequenceMatcher(None, a, b).ratio(), 4)


def _first_non_empty(*values: str | None) -> str | None:
    """Prefer request overrides, then server env."""
    for v in values:
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


class NameSearchRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=500)
    dob: str | None = Field(
        default=None,
        description="Optional birth date (ISO-ish: YYYY, YYYY-MM, or YYYY-MM-DD)",
        max_length=32,
    )
    sources: list[Literal["opensanctions", "aleph", "sayari"]] = Field(
        default_factory=lambda: ["opensanctions", "aleph", "sayari"]
    )
    # Optional overrides from the browser (same pattern as Companies House). Server .env used if omitted.
    opensanctions_api_key: str | None = None
    aleph_api_key: str | None = None
    aleph_api_base: str | None = None
    sayari_client_id: str | None = None
    sayari_client_secret: str | None = None
    sayari_api_base: str | None = None


def _opensanctions_match(api_key: str, name: str, dob: str | None) -> dict[str, Any]:
    """POST /match/default — consolidated OpenSanctions index (FTM entity model)."""
    props: dict[str, list[str]] = {"name": [name.strip()]}
    if dob and dob.strip():
        props["birthDate"] = [dob.strip()]
    body = {
        "queries": {
            "q1": {
                "schema": "Person",
                "properties": props,
            }
        }
    }
    url = f"{OPENSANCTIONS_MATCH_BASE}/default"
    r = requests.post(
        url,
        json=body,
        headers={"Authorization": f"ApiKey {api_key}", "Accept": "application/json"},
        params={"algorithm": "logic-v2"},
        timeout=60,
    )
    if r.status_code >= 400:
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:500]}"}
    data = r.json()
    resp = (data.get("responses") or {}).get("q1") or {}
    raw_results = resp.get("results") or []
    ranked = []
    for ent in raw_results[:25]:
        cap = ent.get("caption") or ""
        props_in = ent.get("properties") or {}
        names = props_in.get("name") or []
        label = cap or (names[0] if names else "")
        ranked.append(
            {
                "id": ent.get("id"),
                "schema": ent.get("schema"),
                "caption": cap,
                "score": _fuzzy_ratio(name, label),
                "datasets": ent.get("datasets"),
            }
        )
    ranked.sort(key=lambda x: -x["score"])
    return {"ok": True, "matches": ranked, "raw_query": resp.get("query")}


def _aleph_search(api_key: str, base_url: str, name: str) -> dict[str, Any]:
    """GET /api/2/entities — same pattern as OCCRP Aleph Pro."""
    url = f"{base_url.rstrip('/')}/entities"
    r = requests.get(
        url,
        params={"q": name.strip(), "limit": 20},
        headers={"Authorization": f"ApiKey {api_key}", "Accept": "application/json"},
        timeout=60,
    )
    if r.status_code >= 400:
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:500]}"}
    data = r.json()
    rows = []
    for entity in data.get("results") or []:
        cap = entity.get("caption") or ""
        rows.append(
            {
                "id": entity.get("id"),
                "schema": entity.get("schema"),
                "caption": cap,
                "score": _fuzzy_ratio(name, cap),
                "datasets": entity.get("datasets"),
                "collection": (entity.get("collection") or {}).get("label"),
            }
        )
    rows.sort(key=lambda x: -x["score"])
    return {"ok": True, "matches": rows}


def _sayari_cache_key(client_id: str, client_secret: str, api_base: str) -> str:
    raw = f"{client_id}\0{client_secret}\0{api_base}".encode()
    return hashlib.sha256(raw).hexdigest()


def _sayari_bearer_token(
    client_id: str, client_secret: str, api_base: str
) -> tuple[str | None, str | None]:
    cache_key = _sayari_cache_key(client_id, client_secret, api_base)
    now = time.time()
    hit = _sayari_token_cache.get(cache_key)
    if hit and now < hit[1]:
        return hit[0], None
    token_url = f"{api_base.rstrip('/')}/oauth/token"
    r = requests.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "audience": "sayari.com",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if r.status_code >= 400:
        return None, f"OAuth {r.status_code}: {r.text[:400]}"
    payload = r.json()
    tok = payload.get("access_token")
    if not tok:
        return None, "No access_token in OAuth response"
    # Cache ~50m (Sayari tokens are typically long-lived)
    _sayari_token_cache[cache_key] = (tok, now + 50 * 60)
    return tok, None


def _sayari_entity_search(
    client_id: str, client_secret: str, api_base: str, name: str, dob: str | None
) -> dict[str, Any]:
    """POST /v1/search/entity — name in q; optional DOB via filter when provided."""
    token, err = _sayari_bearer_token(client_id, client_secret, api_base)
    if err:
        return {"ok": False, "error": err}
    url = f"{api_base.rstrip('/')}/v1/search/entity"
    payload: dict[str, Any] = {"q": name.strip(), "limit": 25}
    # Narrow to person-like search when DOB supplied (Sayari supports date_of_birth field)
    if dob and dob.strip():
        payload["fields"] = ["name", "date_of_birth"]
    r = requests.post(
        url,
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        params={"limit": 25},
        timeout=60,
    )
    if r.status_code >= 400:
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:500]}"}
    data = r.json()
    # EntitySearchResponse: { data: SearchResults[], limit, offset, ... }
    hits = data.get("data")
    if not isinstance(hits, list):
        hits = []
    ranked = []
    for h in hits[:40]:
        if not isinstance(h, dict):
            continue
        label = str(h.get("label") or "")
        ranked.append(
            {
                "score": _fuzzy_ratio(name, label),
                "id": h.get("id"),
                "label": label,
                "entity_url": h.get("entity_url"),
                "countries": h.get("countries"),
                "type": h.get("type"),
                "sanctioned": h.get("sanctioned"),
                "pep": h.get("pep"),
            }
        )
    ranked.sort(key=lambda x: -x["score"])
    return {"ok": True, "matches": ranked}


@router.get("/status")
async def screening_status() -> dict[str, Any]:
    """Which upstream integrations are configured (no secrets)."""
    s = get_settings()
    return {
        "opensanctions": bool(s.OPENSANCTIONS_API_KEY and str(s.OPENSANCTIONS_API_KEY).strip()),
        "aleph": bool(s.ALEPH_API_KEY and str(s.ALEPH_API_KEY).strip()),
        "sayari": bool(
            s.SAYARI_CLIENT_ID
            and str(s.SAYARI_CLIENT_ID).strip()
            and s.SAYARI_CLIENT_SECRET
            and str(s.SAYARI_CLIENT_SECRET).strip()
        ),
        "aleph_api_base": (s.ALEPH_API_BASE or DEFAULT_ALEPH_API).rstrip("/"),
        "sayari_api_base": (s.SAYARI_API_BASE or DEFAULT_SAYARI_API).rstrip("/"),
    }


@router.post("/name-search")
async def name_search(body: NameSearchRequest) -> dict[str, Any]:
    """
    Run selected upstream lookups in parallel (sequential in-process for simplicity).
    Request body may include API keys (browser) or rely on server .env.
    """
    s = get_settings()
    name = body.name.strip()
    out: dict[str, Any] = {
        "query": {"name": name, "dob": body.dob},
        "opensanctions": None,
        "aleph": None,
        "sayari": None,
    }

    if "opensanctions" in body.sources:
        key = _first_non_empty(body.opensanctions_api_key, s.OPENSANCTIONS_API_KEY)
        if not key:
            out["opensanctions"] = {
                "ok": False,
                "skipped": True,
                "error": "OpenSanctions API key missing — set in the app or OPENSANCTIONS_API_KEY on the server",
            }
        else:
            try:
                out["opensanctions"] = _opensanctions_match(key, name, body.dob)
            except requests.RequestException as e:
                logger.exception("OpenSanctions request failed")
                out["opensanctions"] = {"ok": False, "error": str(e)}

    if "aleph" in body.sources:
        key = _first_non_empty(body.aleph_api_key, s.ALEPH_API_KEY)
        base = _first_non_empty(body.aleph_api_base, s.ALEPH_API_BASE) or DEFAULT_ALEPH_API
        if not key:
            out["aleph"] = {
                "ok": False,
                "skipped": True,
                "error": "Aleph API key missing — set in the app or ALEPH_API_KEY on the server",
            }
        else:
            try:
                out["aleph"] = _aleph_search(key, base, name)
            except requests.RequestException as e:
                logger.exception("Aleph request failed")
                out["aleph"] = {"ok": False, "error": str(e)}

    if "sayari" in body.sources:
        cid = _first_non_empty(body.sayari_client_id, s.SAYARI_CLIENT_ID)
        csec = _first_non_empty(body.sayari_client_secret, s.SAYARI_CLIENT_SECRET)
        base = _first_non_empty(body.sayari_api_base, s.SAYARI_API_BASE) or DEFAULT_SAYARI_API
        if not cid or not csec:
            out["sayari"] = {
                "ok": False,
                "skipped": True,
                "error": "Sayari client id/secret missing — set in the app or SAYARI_* on the server",
            }
        else:
            try:
                out["sayari"] = _sayari_entity_search(cid, csec, base, name, body.dob)
            except requests.RequestException as e:
                logger.exception("Sayari request failed")
                out["sayari"] = {"ok": False, "error": str(e)}

    return out
