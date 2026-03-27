"""
Download Companies House filing PDFs for selected transaction IDs.
Uses filing-history index to resolve document_id per transaction (list-then-download pattern).
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

import requests

from .fetch import (
    fetch_document_pdf,
    list_filing_rows_with_documents,
    safe_pdf_filename,
)

log = logging.getLogger(__name__)

# Hard cap per job — avoids timeouts and excessive CH usage
MAX_DOCUMENTS_PER_JOB = 200


def run_document_download(
    api_key: str,
    company_number: str,
    transaction_ids: List[str],
    out_dir: str | Path,
) -> Dict[str, Any]:
    """
    Fetch PDFs for the given transaction_ids. Writes *.pdf into out_dir.
    Returns summary with downloaded count and per-id failures.
    """
    ids = [t.strip() for t in transaction_ids if t and str(t).strip()]
    if not ids:
        return {
            "status": "error",
            "error": "No transaction_ids provided",
            "documents_downloaded": 0,
            "failed": [],
        }

    if len(ids) > MAX_DOCUMENTS_PER_JOB:
        return {
            "status": "error",
            "error": f"Too many filings ({len(ids)}). Maximum per job is {MAX_DOCUMENTS_PER_JOB}.",
            "documents_downloaded": 0,
            "failed": [],
        }

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.auth = (api_key, "")
    session.headers.update({"Accept": "application/json"})
    session_state: Dict[str, float] = {}

    rows = list_filing_rows_with_documents(session, company_number, session_state)
    by_tid: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        tid = row.get("transaction_id")
        if tid:
            by_tid[str(tid)] = row

    saved: List[str] = []
    failed: List[Dict[str, str]] = []

    for tid in ids:
        row = by_tid.get(tid)
        if not row:
            failed.append({"transaction_id": tid, "error": "transaction_not_found_in_history"})
            continue
        doc_id = row.get("document_id")
        if not doc_id:
            failed.append({"transaction_id": tid, "error": "no_document_for_filing"})
            continue
        try:
            pdf = fetch_document_pdf(session, str(doc_id), session_state)
            base = safe_pdf_filename(
                row.get("date"),
                row.get("filing_type"),
                tid,
            )
            fname = f"{base}.pdf"
            (out_path / fname).write_bytes(pdf)
            saved.append(fname)
            log.info("Saved PDF %s for transaction %s", fname, tid)
        except Exception as e:
            log.warning("PDF download failed for %s: %s", tid, e)
            failed.append({"transaction_id": tid, "error": str(e)})

    failures_path = out_path / "download_failures.json"
    if failed:
        with open(failures_path, "w") as f:
            json.dump(failed, f, indent=2)
    elif failures_path.exists():
        failures_path.unlink()

    return {
        "status": "completed",
        "documents_downloaded": len(saved),
        "documents_failed": len(failed),
        "files": saved,
        "failed": failed,
        "out_dir": str(out_path),
    }
