"""
Companies House API fetch — filings, officers, PSC.
Rate-limited, paginated, with retries. No tqdm (backend use).
"""

import json
import logging
import random
import re
import time
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

BASE_URL = "https://api.company-information.service.gov.uk"
# Document binary fetch (same API key auth as public API)
DOCUMENT_API_BASE = "https://document-api.company-information.service.gov.uk"
log = logging.getLogger(__name__)


def _rate_limit(session_state: Dict[str, float], min_interval_s: float = 1.0) -> None:
    """Ensure at least min_interval_s between requests."""
    now = time.time()
    wait = (session_state.get("last_ts", 0) + min_interval_s) - now
    if wait > 0:
        time.sleep(wait)
    session_state["last_ts"] = time.time()


def ch_get(
    session: requests.Session,
    path: str,
    params: Optional[Dict] = None,
    min_interval_s: float = 1.0,
    max_attempts: int = 12,
    session_state: Optional[Dict[str, float]] = None,
) -> dict:
    """
    CH GET with rate limit, 429/5xx retries, exponential backoff.
    """
    state = session_state or {}
    url = f"{BASE_URL}{path}"

    for attempt in range(1, max_attempts + 1):
        _rate_limit(state, min_interval_s)
        r = session.get(url, params=params)

        if r.status_code == 401:
            raise RuntimeError("401 Unauthorized. Check your API key.")

        if r.status_code == 429:
            retry_after = r.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else min(60.0, (2**attempt)) + random.random()
            log.warning("[429] Rate limited. Waiting %.1fs (%d/%d) :: %s", wait, attempt, max_attempts, path)
            time.sleep(wait)
            continue

        if r.status_code in (500, 502, 503, 504):
            wait = min(60.0, (2**attempt)) + random.random()
            log.warning("[%d] Transient. Waiting %.1fs (%d/%d) :: %s", r.status_code, wait, attempt, max_attempts, path)
            time.sleep(wait)
            continue

        r.raise_for_status()
        return r.json()

    raise RuntimeError(f"Failed after {max_attempts} attempts: {url}")


def extract_document_id_from_links(links: Optional[Dict[str, Any]]) -> Optional[str]:
    """Parse document id from filing-history `links.document_metadata` URL."""
    if not links:
        return None
    meta = links.get("document_metadata")
    if not meta or not isinstance(meta, str):
        return None
    if "/document/" not in meta:
        return None
    part = meta.split("/document/", 1)[1].strip("/").split("/")[0]
    return part or None


def filing_year_from_date(date_str: Optional[str]) -> Optional[int]:
    """Calendar year from CH filing date (YYYY-MM-DD or similar)."""
    if not date_str:
        return None
    s = str(date_str).strip()
    if len(s) < 4:
        return None
    try:
        return int(s[:4])
    except ValueError:
        return None


def ch_get_binary(
    session: requests.Session,
    url: str,
    session_state: Dict[str, float],
    *,
    headers: Optional[Dict[str, str]] = None,
    min_interval_s: float = 1.0,
    max_attempts: int = 12,
) -> bytes:
    """GET binary body (PDF etc.) with same rate-limit/retry behaviour as ch_get."""
    h = dict(headers or {})
    for attempt in range(1, max_attempts + 1):
        _rate_limit(session_state, min_interval_s)
        r = session.get(url, headers=h)

        if r.status_code == 401:
            raise RuntimeError("401 Unauthorized. Check your API key.")

        if r.status_code == 429:
            retry_after = r.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else min(60.0, (2**attempt)) + random.random()
            log.warning("[429] Rate limited (binary). Waiting %.1fs :: %s", wait, url)
            time.sleep(wait)
            continue

        if r.status_code in (500, 502, 503, 504):
            wait = min(60.0, (2**attempt)) + random.random()
            log.warning("[%d] Transient (binary). Waiting %.1fs :: %s", r.status_code, wait, url)
            time.sleep(wait)
            continue

        r.raise_for_status()
        return r.content

    raise RuntimeError(f"Failed after {max_attempts} attempts: {url}")


def fetch_document_pdf(session: requests.Session, document_id: str, session_state: Dict[str, float]) -> bytes:
    """Download filing PDF bytes from Document API."""
    url = f"{DOCUMENT_API_BASE}/document/{document_id}/content"
    return ch_get_binary(
        session,
        url,
        session_state,
        headers={"Accept": "application/pdf"},
    )


def safe_pdf_filename(date_str: Optional[str], filing_type: Optional[str], transaction_id: str) -> str:
    """Filesystem-safe base name without extension."""
    d = re.sub(r"[^\w\-]+", "_", (date_str or "nodate")[:32])
    t = re.sub(r"[^\w\-]+", "_", (filing_type or "unknown")[:32])
    tid = re.sub(r"[^\w\-]+", "_", (transaction_id or "")[:24])
    return f"{d}_{t}_{tid}"


def list_filing_rows_with_documents(
    session: requests.Session,
    company_number: str,
    session_state: Dict[str, float],
    max_items: int = 5000,
) -> List[Dict[str, Any]]:
    """
    Full filing history with document availability (metadata only — no PDF bytes).
    """
    cn = company_number.strip().upper()
    items = fetch_all_items_no_bar(
        session,
        f"/company/{cn}/filing-history",
        session_state,
        items_per_page=100,
        max_items=max_items,
    )
    rows: List[Dict[str, Any]] = []
    for it in items:
        links = it.get("links") or {}
        doc_id = extract_document_id_from_links(links)
        rows.append(
            {
                "transaction_id": it.get("transaction_id"),
                "date": it.get("date"),
                "filing_type": it.get("type"),
                "description": it.get("description"),
                "category": it.get("category"),
                "has_document": doc_id is not None,
                "document_id": doc_id,
            }
        )
    return rows


def fetch_all_items(
    session: requests.Session,
    path: str,
    session_state: Dict[str, float],
    items_per_page: int = 100,
    max_items: int = 5000,
) -> List[Dict[str, Any]]:
    """Paginated fetch for officers/PSC."""
    start_index = 0
    all_items: List[Dict[str, Any]] = []

    while len(all_items) < max_items:
        payload = ch_get(
            session,
            path,
            params={"items_per_page": items_per_page, "start_index": start_index},
            session_state=session_state,
        )
        items = payload.get("items") or []
        if not items:
            break
        all_items.extend(items)
        start_index += items_per_page
        total = payload.get("total_results")
        if isinstance(total, int) and start_index >= total:
            break

    return all_items[:max_items]


def fetch_all_items_no_bar(
    session: requests.Session,
    path: str,
    session_state: Dict[str, float],
    items_per_page: int = 100,
    max_items: int = 5000,
) -> List[Dict[str, Any]]:
    """Paginated fetch for filings (no progress bar)."""
    return fetch_all_items(session, path, session_state, items_per_page, max_items)


def get_company_name(session: requests.Session, company_number: str, session_state: Dict[str, float]) -> Optional[str]:
    """Fetch company profile and return company_name."""
    try:
        profile = ch_get(session, f"/company/{company_number}", session_state=session_state)
        return profile.get("company_name")
    except requests.HTTPError:
        return None


def build_filing_history_table(
    session: requests.Session,
    company_numbers: List[str],
    session_state: Dict[str, float],
    per_company_cap: int = 5000,
) -> pd.DataFrame:
    """Build filings DataFrame."""
    rows = []
    for cn in company_numbers:
        log.info("Filings → %s", cn)
        cname = get_company_name(session, cn, session_state)
        items = fetch_all_items_no_bar(
            session,
            f"/company/{cn}/filing-history",
            session_state,
            items_per_page=100,
            max_items=per_company_cap,
        )
        for it in items:
            rows.append({
                "company_name": cname,
                "company_id": cn,
                "filing_date": it.get("date"),
                "filing_type": it.get("type"),
                "category": it.get("category"),
                "description": it.get("description"),
                "transaction_id": it.get("transaction_id"),
            })
    df = pd.DataFrame(rows)
    ordered = ["company_name", "company_id", "filing_date", "filing_type", "category", "description", "transaction_id"]
    return df[[c for c in ordered if c in df.columns]]


def build_officers_table(
    session: requests.Session,
    company_numbers: List[str],
    session_state: Dict[str, float],
    per_company_cap: int = 5000,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build officers DataFrame and failures DataFrame."""
    rows = []
    failures = []
    for cn in company_numbers:
        log.info("Officers → %s", cn)
        try:
            cname = get_company_name(session, cn, session_state)
            items = fetch_all_items(
                session,
                f"/company/{cn}/officers",
                session_state,
                items_per_page=100,
                max_items=per_company_cap,
            )
            for it in items:
                appointed_on = it.get("appointed_on")
                resigned_on = it.get("resigned_on")
                attrs = dict(it)
                for k in ["name", "appointed_on", "resigned_on"]:
                    attrs.pop(k, None)
                rows.append({
                    "company_name": cname,
                    "company_id": cn,
                    "officer_name": it.get("name"),
                    "event_type": "appointment" if appointed_on else ("resignation" if resigned_on else None),
                    "event_date": appointed_on or resigned_on,
                    "attributes_json": json.dumps(attrs, ensure_ascii=False),
                })
        except Exception as e:
            failures.append({"company_id": cn, "stage": "officers", "error": str(e)})
            log.warning("Skipping officers for %s: %s", cn, e)

    return pd.DataFrame(rows), pd.DataFrame(failures)


def build_psc_table(
    session: requests.Session,
    company_numbers: List[str],
    session_state: Dict[str, float],
    per_company_cap: int = 5000,
) -> pd.DataFrame:
    """Build PSC DataFrame."""
    rows = []
    for cn in company_numbers:
        log.info("PSC → %s", cn)
        cname = get_company_name(session, cn, session_state)
        items = fetch_all_items(
            session,
            f"/company/{cn}/persons-with-significant-control",
            session_state,
            items_per_page=100,
            max_items=per_company_cap,
        )
        for it in items:
            date_start = it.get("notified_on") or it.get("started_on")
            date_end = it.get("ceased_on")
            attrs = dict(it)
            for k in ["name", "kind", "notified_on", "started_on", "ceased_on"]:
                attrs.pop(k, None)
            rows.append({
                "company_name": cname,
                "company_id": cn,
                "psc_name": it.get("name") or it.get("title"),
                "psc_type": it.get("kind"),
                "date_start": date_start,
                "date_end": date_end,
                "attributes_json": json.dumps(attrs, ensure_ascii=False),
            })
    return pd.DataFrame(rows)


def resolve_officer_id_to_companies(
    session: requests.Session,
    officer_id: str,
    session_state: Dict[str, float],
    max_companies: int = 100,
) -> List[str]:
    """
    Fetch /officers/{id}/appointments and extract unique company numbers.
    """
    companies: List[str] = []
    start_index = 0
    page_size = 50

    while len(companies) < max_companies:
        payload = ch_get(
            session,
            f"/officers/{officer_id}/appointments",
            params={"items_per_page": page_size, "start_index": start_index},
            session_state=session_state,
        )
        items = payload.get("items") or []
        for appt in items:
            co = appt.get("appointed_to") or {}
            cn = (co.get("company_number") or "").strip().upper()
            if cn and cn not in companies:
                companies.append(cn)
        total = payload.get("total_results", len(items))
        if start_index + len(items) >= total or not items:
            break
        start_index += page_size

    return companies[:max_companies]


def resolve_name_to_companies(
    session: requests.Session,
    query: str,
    session_state: Dict[str, float],
    search_type: str = "officers",
    max_companies: int = 50,
) -> List[str]:
    """
    Search by name: try /search/officers first, then /search (companies).
    Returns company numbers from first matching officer or company results.
    """
    q = query.strip()
    if not q:
        return []

    if search_type == "officers" or search_type == "name":
        # Officer search -> take first officer's appointments
        data = ch_get(
            session,
            "/search/officers",
            params={"q": q, "items_per_page": 5},
            session_state=session_state,
        )
        items = (data or {}).get("items", [])
        for item in items:
            link = (item.get("links") or {}).get("self", "")
            parts = [p for p in link.split("/") if p]
            officer_id = parts[1] if len(parts) >= 2 else ""
            if officer_id:
                companies = resolve_officer_id_to_companies(session, officer_id, session_state, max_companies)
                if companies:
                    return companies

    # Company search
    data = ch_get(
        session,
        "/search",
        params={"q": q, "items_per_page": max_companies},
        session_state=session_state,
    )
    items = (data or {}).get("items", [])
    companies = []
    for item in items:
        cn = (item.get("company_number") or "").strip().upper()
        if cn:
            companies.append(cn)
    return companies[:max_companies]
