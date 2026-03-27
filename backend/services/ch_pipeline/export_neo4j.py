"""
Export CH data to Aura/Neo4j importer CSVs.
Normalises persons, addresses, filings; builds node/relationship CSVs.
"""

import json
import re
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

TITLE_WORDS = {"MR", "MRS", "MS", "MISS", "DR", "PROF", "SIR", "LORD", "LADY", "DAME"}


def sha1_hex(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def norm_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def normalize_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    s = name.upper()
    s = re.sub(r"[^A-Z0-9\s]", " ", s)
    parts = [p for p in norm_spaces(s).split(" ") if p]
    parts = [p for p in parts if p not in TITLE_WORDS]
    return " ".join(parts) if parts else None


def get_dob_from_attrs(attrs: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    dob = attrs.get("date_of_birth") or {}
    y, m = dob.get("year"), dob.get("month")
    try:
        y = int(y) if y is not None else None
    except (TypeError, ValueError):
        y = None
    try:
        m = int(m) if m is not None else None
    except (TypeError, ValueError):
        m = None
    return y, m


def person_id_from_name_dob(
    norm_name: Optional[str], dob_year: Optional[int], dob_month: Optional[int]
) -> Optional[str]:
    if not norm_name:
        return None
    key = f"{norm_name}|{dob_year or ''}|{dob_month or ''}"
    return sha1_hex(key)


def normalize_postcode(pc: Optional[str]) -> Optional[str]:
    if not pc:
        return None
    s = pc.upper()
    s = re.sub(r"[^A-Z0-9]", "", s)
    return s or None


def normalize_address(addr: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Returns (normalized_full, postcode_norm, locality, country)."""
    if not isinstance(addr, dict) or not addr:
        return None, None, None, None
    parts = []
    for k in ["premises", "address_line_1", "address_line_2", "locality", "region", "postal_code", "country"]:
        v = addr.get(k)
        if v:
            parts.append(str(v))
    full = ", ".join(parts)
    full_u = full.upper()
    full_u = re.sub(r"[^A-Z0-9,\s]", " ", full_u)
    full_u = norm_spaces(full_u)
    postcode = addr.get("postal_code") or addr.get("postcode")
    pc_norm = normalize_postcode(postcode)
    locality = addr.get("locality")
    country = addr.get("country")
    return full_u or None, pc_norm, (str(locality) if locality else None), (str(country) if country else None)


def address_id_from_normalized(addr_norm: Optional[str]) -> Optional[str]:
    if not addr_norm:
        return None
    return sha1_hex(addr_norm)


def safe_json_loads(s: Any) -> Dict[str, Any]:
    if isinstance(s, dict):
        return s
    if not s or not isinstance(s, str):
        return {}
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return {}


def extract_best_name(
    officer_name: Optional[str], psc_name: Optional[str], attrs: Dict[str, Any]
) -> Optional[str]:
    if officer_name:
        return officer_name
    if psc_name:
        return psc_name
    ne = attrs.get("name_elements") or {}
    forename = ne.get("forename")
    surname = ne.get("surname")
    title = ne.get("title")
    if forename or surname:
        display = " ".join([x for x in [title, forename, surname] if x])
        return display.strip() if display else None
    return attrs.get("name") or attrs.get("title")


def export_for_aura_data_importer(
    df_filings: pd.DataFrame,
    df_officers: pd.DataFrame,
    df_psc: pd.DataFrame,
    out_dir: str | Path = ".",
) -> Dict[str, pd.DataFrame]:
    """Export CH DataFrames to Aura-style CSVs. Returns dict of DataFrames."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    companies = pd.concat([
        df_filings[["company_id", "company_name"]]
        if {"company_id", "company_name"} <= set(df_filings.columns)
        else pd.DataFrame(columns=["company_id", "company_name"]),
        df_officers[["company_id", "company_name"]]
        if {"company_id", "company_name"} <= set(df_officers.columns)
        else pd.DataFrame(columns=["company_id", "company_name"]),
        df_psc[["company_id", "company_name"]]
        if {"company_id", "company_name"} <= set(df_psc.columns)
        else pd.DataFrame(columns=["company_id", "company_name"]),
    ], ignore_index=True)
    companies = companies.dropna(subset=["company_id"]).drop_duplicates()
    companies = companies.rename(columns={"company_id": "company_number", "company_name": "name"})
    companies["company_number"] = companies["company_number"].astype(str)

    filings = df_filings.copy()
    if "company_id" not in filings.columns:
        filings["company_id"] = None

    def make_filing_id(row):
        tid = row.get("transaction_id")
        if isinstance(tid, str) and tid.strip():
            return tid.strip()
        key = f"{row.get('company_id','')}|{row.get('filing_date','')}|{row.get('filing_type','')}|{row.get('description','')}"
        return sha1_hex(key)

    if "filing_date" in filings.columns:
        filings["filing_date"] = filings["filing_date"].astype(str)
    filings["filing_id"] = filings.apply(make_filing_id, axis=1)

    filings_nodes = filings[["filing_id"]].copy()
    for col in ["filing_date", "filing_type", "description", "category", "transaction_id"]:
        if col in filings.columns:
            if col == "filing_date":
                filings_nodes["date"] = filings[col]
            elif col == "filing_type":
                filings_nodes["type"] = filings[col]
            else:
                filings_nodes[col] = filings[col]
    filings_nodes = filings_nodes.drop_duplicates(subset=["filing_id"])

    rel_company_filed = filings[["company_id", "filing_id"]].rename(columns={"company_id": "company_number"})
    rel_company_filed["company_number"] = rel_company_filed["company_number"].astype(str)
    rel_company_filed = rel_company_filed.dropna(subset=["company_number", "filing_id"]).drop_duplicates()

    dates = pd.DataFrame()
    rel_filing_date = pd.DataFrame()
    if "date" in filings_nodes.columns:
        dates = filings_nodes[["date"]].dropna().drop_duplicates().rename(columns={"date": "date"})
        rel_filing_date = filings_nodes[["filing_id", "date"]].dropna().drop_duplicates()

    people_rows: Dict[str, Dict] = {}
    address_rows: Dict[str, Dict] = {}
    rel_officer_rows = []
    rel_psc_rows = []
    rel_person_address_rows = []

    def upsert_person(pid, display_name, norm_name, dob_year, dob_month, nationality, cor, extra):
        if not pid:
            return
        existing = people_rows.get(pid, {})

        def pick(a, b):
            return a if a not in (None, "", []) else b

        people_rows[pid] = {
            "person_id": pid,
            "name_full": pick(existing.get("name_full"), display_name),
            "name_normalized": pick(existing.get("name_normalized"), norm_name),
            "dob_year": pick(existing.get("dob_year"), dob_year),
            "dob_month": pick(existing.get("dob_month"), dob_month),
            "nationality": pick(existing.get("nationality"), nationality),
            "country_of_residence": pick(existing.get("country_of_residence"), cor),
        }

    def upsert_address(aid, normalized, postcode, locality, country):
        if not aid:
            return
        existing = address_rows.get(aid, {})

        def pick(a, b):
            return a if a not in (None, "", []) else b

        address_rows[aid] = {
            "address_id": aid,
            "normalized": pick(existing.get("normalized"), normalized),
            "postcode": pick(existing.get("postcode"), postcode),
            "locality": pick(existing.get("locality"), locality),
            "country": pick(existing.get("country"), country),
        }

    for _, row in df_officers.iterrows():
        cn = str(row.get("company_id")) if row.get("company_id") is not None else None
        attrs = safe_json_loads(row.get("attributes_json"))
        display_name = extract_best_name(row.get("officer_name"), None, attrs)
        norm_name = normalize_name(display_name)
        dob_year, dob_month = get_dob_from_attrs(attrs)
        pid = person_id_from_name_dob(norm_name, dob_year, dob_month)
        upsert_person(
            pid, display_name, norm_name, dob_year, dob_month,
            attrs.get("nationality"), attrs.get("country_of_residence"), attrs
        )
        addr = attrs.get("address") or {}
        addr_norm, pc_norm, locality, country = normalize_address(addr)
        aid = address_id_from_normalized(addr_norm)
        upsert_address(aid, addr_norm, pc_norm, locality, country)
        if pid and aid:
            rel_person_address_rows.append({"person_id": pid, "address_id": aid, "address_type": "service"})
        rel_officer_rows.append({
            "person_id": pid,
            "company_number": cn,
            "role": attrs.get("officer_role") or row.get("role"),
            "appointed_on": row.get("event_date") if row.get("event_type") == "appointment" else attrs.get("appointed_on"),
            "resigned_on": row.get("event_date") if row.get("event_type") == "resignation" else attrs.get("resigned_on"),
            "source_link": (attrs.get("links") or {}).get("self"),
        })

    for _, row in df_psc.iterrows():
        cn = str(row.get("company_id")) if row.get("company_id") is not None else None
        attrs = safe_json_loads(row.get("attributes_json"))
        display_name = extract_best_name(None, row.get("psc_name"), attrs)
        norm_name = normalize_name(display_name)
        dob_year, dob_month = get_dob_from_attrs(attrs)
        pid = person_id_from_name_dob(norm_name, dob_year, dob_month)
        upsert_person(
            pid, display_name, norm_name, dob_year, dob_month,
            attrs.get("nationality"), attrs.get("country_of_residence"), attrs
        )
        addr = attrs.get("address") or {}
        addr_norm, pc_norm, locality, country = normalize_address(addr)
        aid = address_id_from_normalized(addr_norm)
        upsert_address(aid, addr_norm, pc_norm, locality, country)
        if pid and aid:
            rel_person_address_rows.append({"person_id": pid, "address_id": aid, "address_type": "service"})
        natures = attrs.get("natures_of_control") or row.get("natures_of_control") or []
        natures_str = "|".join([str(x) for x in natures]) if isinstance(natures, list) else str(natures)
        rel_psc_rows.append({
            "person_id": pid,
            "company_number": cn,
            "psc_kind": row.get("psc_type") or attrs.get("kind"),
            "notified_on": row.get("date_start") or attrs.get("notified_on") or attrs.get("started_on"),
            "ceased_on": row.get("date_end") or attrs.get("ceased_on"),
            "natures_of_control": natures_str,
            "source_link": (attrs.get("links") or {}).get("self"),
        })

    people = pd.DataFrame(list(people_rows.values()))
    addresses = pd.DataFrame(list(address_rows.values()))
    rel_officer = pd.DataFrame(rel_officer_rows).dropna(subset=["person_id", "company_number"])
    rel_psc = pd.DataFrame(rel_psc_rows).dropna(subset=["person_id", "company_number"])
    rel_person_address = pd.DataFrame(rel_person_address_rows).dropna(subset=["person_id", "address_id"])
    rel_officer = rel_officer.drop_duplicates(
        subset=["person_id", "company_number", "role", "appointed_on", "resigned_on"]
    )
    rel_psc = rel_psc.drop_duplicates(
        subset=["person_id", "company_number", "psc_kind", "notified_on", "ceased_on", "natures_of_control"]
    )
    rel_person_address = rel_person_address.drop_duplicates(subset=["person_id", "address_id", "address_type"])

    out_path = Path(out_dir)
    companies.to_csv(out_path / "companies.csv", index=False)
    people.to_csv(out_path / "people.csv", index=False)
    addresses.to_csv(out_path / "addresses.csv", index=False)
    filings_nodes.to_csv(out_path / "filings.csv", index=False)
    if not dates.empty:
        dates.to_csv(out_path / "dates.csv", index=False)
    rel_officer.to_csv(out_path / "rel_officer.csv", index=False)
    rel_psc.to_csv(out_path / "rel_psc.csv", index=False)
    rel_person_address.to_csv(out_path / "rel_person_address.csv", index=False)
    rel_company_filed.to_csv(out_path / "rel_company_filed.csv", index=False)
    if not rel_filing_date.empty:
        rel_filing_date.to_csv(out_path / "rel_filing_date.csv", index=False)

    return {
        "companies": companies,
        "people": people,
        "addresses": addresses,
        "filings": filings_nodes,
        "dates": dates,
        "rel_officer": rel_officer,
        "rel_psc": rel_psc,
        "rel_person_address": rel_person_address,
        "rel_company_filed": rel_company_filed,
        "rel_filing_date": rel_filing_date,
    }
