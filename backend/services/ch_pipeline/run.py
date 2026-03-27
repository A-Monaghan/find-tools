"""
CH pipeline entrypoint: resolve search → fetch → export.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

import requests

from .export_neo4j import export_for_aura_data_importer
from .fetch import (
    build_filing_history_table,
    build_officers_table,
    build_psc_table,
    resolve_name_to_companies,
    resolve_officer_id_to_companies,
)

log = logging.getLogger(__name__)

# Max companies per run to avoid overload
MAX_COMPANIES = 100


def resolve_to_company_numbers(
    api_key: str,
    search_type: str,
    search_value: str,
) -> List[str]:
    """
    Resolve search_type + search_value to list of company numbers.
    - company_number: comma-separated numbers
    - officer_id: /officers/{id}/appointments
    - name: /search/officers or /search
    """
    value = (search_value or "").strip()
    if not value:
        return []

    session = requests.Session()
    session.auth = (api_key, "")
    session.headers.update({"Accept": "application/json"})
    session_state: Dict[str, float] = {}

    if search_type == "company_number":
        parts = [p.strip().upper() for p in value.split(",") if p.strip()]
        return list(dict.fromkeys(parts))[:MAX_COMPANIES]

    if search_type == "officer_id":
        return resolve_officer_id_to_companies(session, value, session_state, MAX_COMPANIES)

    if search_type in ("name", "officers"):
        return resolve_name_to_companies(session, value, session_state, "officers", MAX_COMPANIES)

    # Fallback: treat as company_number
    return [value.upper()]


def run_pipeline(
    api_key: str,
    company_numbers: List[str],
    out_dir: str | Path,
    per_company_cap: int = 5000,
) -> Dict[str, Any]:
    """
    Run full CH pipeline: fetch filings, officers, PSC; export to Neo4j CSVs.
    Returns summary dict with counts and file paths.
    """
    if not company_numbers:
        return {"error": "No company numbers to process", "filings": 0, "officers": 0, "psc": 0}

    company_numbers = company_numbers[:MAX_COMPANIES]
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.auth = (api_key, "")
    session.headers.update({"Accept": "application/json"})
    session_state: Dict[str, float] = {}

    log.info("Fetching CH data for %d companies", len(company_numbers))
    df_filings = build_filing_history_table(session, company_numbers, session_state, per_company_cap)
    df_officers, df_officers_fail = build_officers_table(
        session, company_numbers, session_state, per_company_cap
    )
    df_psc = build_psc_table(session, company_numbers, session_state, per_company_cap)

    # Save raw CSVs
    df_officers_fail.to_csv(out_path / "officers_failures.csv", index=False)
    df_filings.to_csv(out_path / "filing_history.csv", index=False)
    df_officers.to_csv(out_path / "officers.csv", index=False)
    df_psc.to_csv(out_path / "psc.csv", index=False)

    # Export Neo4j CSVs
    export_for_aura_data_importer(df_filings, df_officers, df_psc, out_dir=out_path)

    files = [
        "filing_history.csv",
        "officers.csv",
        "psc.csv",
        "officers_failures.csv",
        "companies.csv",
        "people.csv",
        "addresses.csv",
        "filings.csv",
        "rel_officer.csv",
        "rel_psc.csv",
        "rel_person_address.csv",
        "rel_company_filed.csv",
    ]
    existing = [f for f in files if (out_path / f).exists()]

    return {
        "status": "completed",
        "companies_processed": len(company_numbers),
        "filings": len(df_filings),
        "officers": len(df_officers),
        "psc": len(df_psc),
        "officer_failures": len(df_officers_fail),
        "files": existing,
        "out_dir": str(out_path),
    }
