"""
Companies House pipeline API.

Resolves search (company number, officer ID, name) → fetches CH data → exports Neo4j CSVs.
Jobs stored per-run; delete manually via UI. Set CH_JOB_EXPIRY_HOURS>0 for optional auto-cleanup.
"""

import io
import json
import shutil
import time
import uuid
import zipfile
from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from core.config import get_settings
from models.schemas import (
    CHDocumentsDownloadRequest,
    CHFilingsListRequest,
    CHFilingsListResponse,
    CHFilingListItem,
    CHHopGraphRequest,
    CHRunRequest,
)
from services.ch_pipeline.ch_graph import get_company_hop_graph
from services.ch_pipeline.document_download import run_document_download
from services.ch_pipeline.fetch import filing_year_from_date, list_filing_rows_with_documents
from services.ch_pipeline.run import resolve_to_company_numbers, run_pipeline

router = APIRouter(prefix="/ch", tags=["companies-house"])


def _get_api_key(override: str | None) -> str:
    """Use override if provided, else env."""
    if override and override.strip():
        return override.strip()
    settings = get_settings()
    key = settings.COMPANIES_HOUSE_API_KEY
    if not key or not str(key).strip():
        raise HTTPException(
            status_code=400,
            detail="Companies House API key required. Set COMPANIES_HOUSE_API_KEY or provide in request.",
        )
    return str(key).strip()


def _cleanup_expired_jobs(base_dir: Path, expiry_hours: int) -> None:
    """Remove job dirs older than expiry_hours. No-op if expiry_hours <= 0."""
    if expiry_hours <= 0 or not base_dir.exists():
        return
    cutoff = time.time() - (expiry_hours * 3600)
    for d in base_dir.iterdir():
        if d.is_dir() and len(d.name) == 36:  # uuid format
            try:
                if d.stat().st_mtime < cutoff:
                    shutil.rmtree(d)
            except OSError:
                pass


def _list_jobs(base_dir: Path, expiry_hours: int = 0) -> list[dict]:
    """List valid jobs with metadata. Optionally cleans expired if expiry_hours > 0."""
    if expiry_hours > 0:
        _cleanup_expired_jobs(base_dir, expiry_hours)
    jobs = []
    if not base_dir.exists():
        return jobs
    for d in sorted(base_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir() or len(d.name) != 36:
            continue
        meta_path = d / "metadata.json"
        if not meta_path.exists():
            continue
        try:
            with open(meta_path) as f:
                meta = json.load(f)
            meta["job_id"] = d.name
            meta["created_at"] = meta.get("created_at", d.stat().st_mtime)
            jobs.append(meta)
        except (json.JSONDecodeError, OSError):
            pass
    return jobs


@router.post("/run")
async def run_ch_pipeline(request: CHRunRequest):
    """
    Run CH pipeline: resolve search → fetch → export.
    Returns job_id for download. Jobs kept until manually deleted (or auto-expire if CH_JOB_EXPIRY_HOURS>0).
    """
    key = _get_api_key(request.api_key)
    settings = get_settings()
    base_dir = settings.CH_PIPELINE_OUTPUT_DIR
    base_dir.mkdir(parents=True, exist_ok=True)

    if settings.CH_JOB_EXPIRY_HOURS > 0:
        _cleanup_expired_jobs(base_dir, settings.CH_JOB_EXPIRY_HOURS)

    job_id = str(uuid.uuid4())
    out_dir = base_dir / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    company_numbers = resolve_to_company_numbers(key, request.search_type, request.search_value)
    if not company_numbers:
        raise HTTPException(
            status_code=400,
            detail=f"No companies resolved for search_type={request.search_type}, search_value={request.search_value!r}",
        )

    try:
        result = run_pipeline(key, company_numbers, out_dir)
    except RuntimeError as e:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise HTTPException(status_code=502, detail=str(e))

    # Write metadata for job list
    meta = {
        "created_at": time.time(),
        "search_type": request.search_type,
        "search_value": request.search_value,
        "companies_processed": result.get("companies_processed"),
        "filings": result.get("filings"),
        "officers": result.get("officers"),
        "psc": result.get("psc"),
    }
    with open(out_dir / "metadata.json", "w") as f:
        json.dump(meta, f)

    result["job_id"] = job_id
    return result


@router.post("/filings/list", response_model=CHFilingsListResponse)
async def list_ch_filings(request: CHFilingsListRequest):
    """
    List filing metadata for one company (no PDFs). Optional year_from / year_to filter on filing date.
    Use this before POST /ch/documents/download to pick transaction_ids.
    """
    key = _get_api_key(request.api_key)
    settings = get_settings()
    base_dir = settings.CH_PIPELINE_OUTPUT_DIR
    base_dir.mkdir(parents=True, exist_ok=True)

    if settings.CH_JOB_EXPIRY_HOURS > 0:
        _cleanup_expired_jobs(base_dir, settings.CH_JOB_EXPIRY_HOURS)

    session = requests.Session()
    session.auth = (key, "")
    session.headers.update({"Accept": "application/json"})
    session_state: dict[str, float] = {}

    cn = request.company_number.strip().upper()
    try:
        rows_raw = list_filing_rows_with_documents(session, cn, session_state)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    yf, yt = request.year_from, request.year_to
    filings: list[CHFilingListItem] = []
    for row in rows_raw:
        if yf is not None or yt is not None:
            y = filing_year_from_date(row.get("date"))
            if y is None:
                continue
            if yf is not None and y < yf:
                continue
            if yt is not None and y > yt:
                continue
        filings.append(CHFilingListItem(**row))

    return CHFilingsListResponse(company_number=cn, filings=filings)


@router.post("/documents/download")
async def download_ch_documents(request: CHDocumentsDownloadRequest):
    """
    Download PDFs for selected filing transaction IDs (from /ch/filings/list). Returns job_id; zip via GET /ch/download/{job_id}.
    """
    key = _get_api_key(request.api_key)
    settings = get_settings()
    base_dir = settings.CH_PIPELINE_OUTPUT_DIR
    base_dir.mkdir(parents=True, exist_ok=True)

    if settings.CH_JOB_EXPIRY_HOURS > 0:
        _cleanup_expired_jobs(base_dir, settings.CH_JOB_EXPIRY_HOURS)

    job_id = str(uuid.uuid4())
    out_dir = base_dir / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    cn = request.company_number.strip().upper()
    try:
        result = run_document_download(key, cn, request.transaction_ids, out_dir)
    except Exception as e:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise HTTPException(status_code=502, detail=str(e))

    if result.get("status") == "error":
        shutil.rmtree(out_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=result.get("error", "Download failed"))

    meta = {
        "created_at": time.time(),
        "search_type": "documents",
        "search_value": cn,
        "job_kind": "documents",
        "companies_processed": 1,
        "documents_downloaded": result.get("documents_downloaded"),
        "documents_failed": result.get("documents_failed"),
        "filings": None,
    }
    with open(out_dir / "metadata.json", "w") as f:
        json.dump(meta, f)

    result["job_id"] = job_id
    return result


@router.get("/jobs")
async def list_ch_jobs():
    """List all saved jobs. Delete via DELETE /ch/jobs/{job_id}."""
    settings = get_settings()
    jobs = _list_jobs(settings.CH_PIPELINE_OUTPUT_DIR, settings.CH_JOB_EXPIRY_HOURS)
    return {"jobs": jobs}


@router.post("/graph/hops")
async def get_ch_hop_graph(request: CHHopGraphRequest):
    """
    Return a company-centred N-hop graph for CH relationships from Neo4j.
    Used by frontend visual map in the CH pipeline tab.
    """
    try:
        result = get_company_hop_graph(
            company_number=request.company_number,
            hops=request.hops,
            max_nodes=request.max_nodes,
            max_edges=request.max_edges,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j unavailable: {e}")

    if result.get("error"):
        detail = str(result["error"])
        if detail.startswith("Company not found:"):
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=400, detail=detail)
    return result


@router.delete("/jobs/{job_id}")
async def delete_ch_job(job_id: str):
    """Delete a job and its output files."""
    settings = get_settings()
    out_dir = settings.CH_PIPELINE_OUTPUT_DIR / job_id
    if not out_dir.exists() or not out_dir.is_dir() or len(job_id) != 36:
        raise HTTPException(status_code=404, detail="Job not found.")
    try:
        shutil.rmtree(out_dir)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete: {e}")
    return {"message": "Job deleted"}


@router.get("/download")
@router.get("/download/{job_id}")
async def download_ch_artefacts(job_id: str | None = None):
    """
    Return a zip of CH pipeline CSVs and/or filing PDFs.
    GET /ch/download — latest job (backwards compat).
    GET /ch/download/{job_id} — specific job.
    """
    settings = get_settings()
    base_dir = settings.CH_PIPELINE_OUTPUT_DIR

    if job_id:
        out_dir = base_dir / job_id
    else:
        # Latest: most recent job dir
        jobs = _list_jobs(base_dir, settings.CH_JOB_EXPIRY_HOURS)
        if not jobs:
            raise HTTPException(status_code=404, detail="No CH pipeline output found. Run the pipeline first.")
        out_dir = base_dir / jobs[0]["job_id"]

    if not out_dir.exists() or not out_dir.is_dir():
        raise HTTPException(status_code=404, detail="Job not found or expired.")

    csv_files = sorted(out_dir.glob("*.csv"))
    pdf_files = sorted(out_dir.glob("*.pdf"))
    extra = []
    fail_json = out_dir / "download_failures.json"
    if fail_json.exists():
        extra.append(fail_json)
    to_zip = csv_files + pdf_files + [f for f in extra if f not in csv_files + pdf_files]
    if not to_zip:
        raise HTTPException(status_code=404, detail="No CSV or PDF files for this job.")

    job_kind = "csv"
    meta_path = out_dir / "metadata.json"
    if meta_path.exists():
        try:
            with open(meta_path) as f:
                job_kind = json.load(f).get("job_kind") or job_kind
        except (json.JSONDecodeError, OSError):
            pass
    if job_kind != "documents" and pdf_files and not csv_files:
        job_kind = "documents"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in to_zip:
            zf.write(f, f.name)

    buffer.seek(0)
    prefix = "ch_documents" if job_kind == "documents" else "ch_pipeline"
    filename = f"{prefix}_{job_id or 'latest'}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
