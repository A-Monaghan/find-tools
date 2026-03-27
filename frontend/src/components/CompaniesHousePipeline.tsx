/**
 * Companies House pipeline UI.
 * Two text inputs: CH API key, search value. Dropdown: search type.
 * Run pipeline → fetch CH data → export Neo4j CSVs.
 * Sessions listed with download and delete options.
 */
import React, { useState, useCallback, useEffect, useMemo, useRef, lazy, Suspense } from 'react';
import { Building2, Download, Play, ChevronDown, FileText, Share2 } from 'lucide-react';

// Heavy graph lib — load only when user opens the map (keeps initial bundle smaller).
const ForceGraph2D = lazy(() => import('react-force-graph-2d'));
import {
  runCHPipeline,
  listCHJobs,
  getCHDownloadUrl,
  listCHFilings,
  downloadCHDocuments,
  getCHHopGraph,
  type CHJob,
  type CHHopGraphResponse,
  type CHFilingListItem,
} from '../services/api';
import Spinner from './Spinner';
import { loadDraftValue, saveDraftValue } from '../utils/draftState';

type SearchType = 'company_number' | 'officer_id' | 'name';
const CH_DRAFT_PREFIX = 'rag_v2_draft_ch_pipeline_';

const SEARCH_TYPE_OPTIONS: { value: SearchType; label: string }[] = [
  { value: 'company_number', label: 'Company number' },
  { value: 'officer_id', label: 'Officer ID' },
  { value: 'name', label: 'Name' },
];

interface CompaniesHousePipelineProps {
  apiKey?: string;
}

export const CompaniesHousePipeline: React.FC<CompaniesHousePipelineProps> = ({ apiKey: apiKeyProp }) => {
  const [searchValue, setSearchValue] = useState(() =>
    loadDraftValue(`${CH_DRAFT_PREFIX}search_value`)
  );
  const [searchType, setSearchType] = useState<SearchType>(() => {
    const saved = loadDraftValue(`${CH_DRAFT_PREFIX}search_type`, 'company_number');
    return saved === 'officer_id' || saved === 'name' ? saved : 'company_number';
  });
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{
    job_id?: string;
    companies_processed?: number;
    filings?: number;
    officers?: number;
    psc?: number;
    officer_failures?: number;
    files?: string[];
  } | null>(null);
  const [jobs, setJobs] = useState<CHJob[]>([]);

  // Filing PDFs: list-then-download (one company number)
  const [docCompany, setDocCompany] = useState(() =>
    loadDraftValue(`${CH_DRAFT_PREFIX}doc_company`)
  );
  const [docYearFrom, setDocYearFrom] = useState<string>(() =>
    loadDraftValue(`${CH_DRAFT_PREFIX}doc_year_from`)
  );
  const [docYearTo, setDocYearTo] = useState<string>(() =>
    loadDraftValue(`${CH_DRAFT_PREFIX}doc_year_to`)
  );
  const [docFilings, setDocFilings] = useState<CHFilingListItem[]>([]);
  const [docSelected, setDocSelected] = useState<Set<string>>(new Set());
  const [docListLoading, setDocListLoading] = useState(false);
  const [docDownLoading, setDocDownLoading] = useState(false);
  const [docError, setDocError] = useState<string | null>(null);
  const [docResult, setDocResult] = useState<{ job_id?: string; downloaded?: number; failed?: number } | null>(null);
  const [graphCompany, setGraphCompany] = useState(() =>
    loadDraftValue(`${CH_DRAFT_PREFIX}graph_company`)
  );
  const [graphHops, setGraphHops] = useState<number>(() => {
    const raw = loadDraftValue(`${CH_DRAFT_PREFIX}graph_hops`, '2');
    const n = Number.parseInt(raw, 10);
    return Number.isFinite(n) && n >= 1 && n <= 4 ? n : 2;
  });
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [graphResult, setGraphResult] = useState<CHHopGraphResponse | null>(null);
  const graphWrapRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<any>(null);
  const [graphSize, setGraphSize] = useState({ width: 860, height: 420 });
  const filingsAbortRef = useRef<AbortController | null>(null);
  const graphAbortRef = useRef<AbortController | null>(null);

  const loadJobs = useCallback(async () => {
    try {
      const { jobs: j } = await listCHJobs();
      setJobs(j);
    } catch {
      setJobs([]);
    }
  }, []);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  // Keep draft form inputs across refreshes/tab switches.
  useEffect(() => {
    saveDraftValue(`${CH_DRAFT_PREFIX}search_value`, searchValue);
  }, [searchValue]);

  useEffect(() => {
    saveDraftValue(`${CH_DRAFT_PREFIX}search_type`, searchType);
  }, [searchType]);

  useEffect(() => {
    saveDraftValue(`${CH_DRAFT_PREFIX}doc_company`, docCompany);
  }, [docCompany]);

  useEffect(() => {
    saveDraftValue(`${CH_DRAFT_PREFIX}doc_year_from`, docYearFrom);
  }, [docYearFrom]);

  useEffect(() => {
    saveDraftValue(`${CH_DRAFT_PREFIX}doc_year_to`, docYearTo);
  }, [docYearTo]);
  useEffect(() => {
    saveDraftValue(`${CH_DRAFT_PREFIX}graph_company`, graphCompany);
  }, [graphCompany]);

  useEffect(() => {
    saveDraftValue(`${CH_DRAFT_PREFIX}graph_hops`, String(graphHops));
  }, [graphHops]);

  useEffect(() => {
    const el = graphWrapRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const width = Math.max(Math.floor(entry.contentRect.width), 320);
      setGraphSize({ width, height: 420 });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    return () => {
      filingsAbortRef.current?.abort();
      graphAbortRef.current?.abort();
    };
  }, []);

  const handleRun = useCallback(async () => {
    const value = searchValue.trim();
    if (!value) {
      setError('Enter a search value.');
      return;
    }
    setError(null);
    setResult(null);
    setIsLoading(true);
    try {
      const res = await runCHPipeline(
        searchType,
        value,
        (apiKeyProp ?? '').trim() || undefined
      );
      if (res.error) {
        setError(res.error);
      } else {
        setResult({
          job_id: res.job_id,
          companies_processed: res.companies_processed,
          filings: res.filings,
          officers: res.officers,
          psc: res.psc,
          officer_failures: res.officer_failures,
          files: res.files,
        });
        await loadJobs();
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Pipeline failed.');
    } finally {
      setIsLoading(false);
    }
  }, [apiKeyProp, searchValue, searchType, loadJobs]);

  const parseYear = (s: string): number | null => {
    const n = parseInt(s.trim(), 10);
    return Number.isFinite(n) && n >= 1800 && n <= 2100 ? n : null;
  };

  const handleListFilings = useCallback(async () => {
    const cn = docCompany.trim();
    if (!cn) {
      setDocError('Enter a company number.');
      return;
    }
    setDocError(null);
    setDocResult(null);
    setDocListLoading(true);
    setDocFilings([]);
    setDocSelected(new Set());
    try {
      filingsAbortRef.current?.abort();
      const controller = new AbortController();
      filingsAbortRef.current = controller;
      const yf = docYearFrom.trim() ? parseYear(docYearFrom) : null;
      const yt = docYearTo.trim() ? parseYear(docYearTo) : null;
      if (docYearFrom.trim() && yf === null) {
        setDocError('Invalid year (from).');
        return;
      }
      if (docYearTo.trim() && yt === null) {
        setDocError('Invalid year (to).');
        return;
      }
      if (yf !== null && yt !== null && yf > yt) {
        setDocError('Year (from) must be ≤ year (to).');
        return;
      }
      const res = await listCHFilings(cn, {
        yearFrom: yf,
        yearTo: yt,
        apiKey: (apiKeyProp ?? '').trim() || undefined,
      }, controller.signal);
      setDocFilings(res.filings);
    } catch (e: unknown) {
      setDocError(e instanceof Error ? e.message : 'Could not list filings.');
    } finally {
      setDocListLoading(false);
    }
  }, [apiKeyProp, docCompany, docYearFrom, docYearTo]);

  const toggleDocRow = useCallback((tid: string | null, hasDoc: boolean) => {
    if (!tid || !hasDoc) return;
    setDocSelected((prev) => {
      const next = new Set(prev);
      if (next.has(tid)) next.delete(tid);
      else next.add(tid);
      return next;
    });
  }, []);

  const selectAllWithPdf = useCallback(() => {
    const tids = docFilings.filter((f) => f.has_document && f.transaction_id).map((f) => f.transaction_id as string);
    setDocSelected(new Set(tids));
  }, [docFilings]);

  const handleDownloadPdfs = useCallback(async () => {
    const cn = docCompany.trim();
    if (!cn) {
      setDocError('Enter a company number.');
      return;
    }
    if (docSelected.size === 0) {
      setDocError('Select at least one filing that has a PDF (tick the row).');
      return;
    }
    setDocError(null);
    setDocResult(null);
    setDocDownLoading(true);
    try {
      const res = await downloadCHDocuments(cn, Array.from(docSelected), (apiKeyProp ?? '').trim() || undefined);
      if (res.error) {
        setDocError(res.error);
      } else {
        setDocResult({
          job_id: res.job_id,
          downloaded: res.documents_downloaded,
          failed: res.documents_failed,
        });
        await loadJobs();
      }
    } catch (e: unknown) {
      setDocError(e instanceof Error ? e.message : 'Download failed.');
    } finally {
      setDocDownLoading(false);
    }
  }, [apiKeyProp, docCompany, docSelected, loadJobs]);

  const handleLoadGraph = useCallback(async () => {
    const company = graphCompany.trim().toUpperCase();
    if (!company) {
      setGraphError('Enter a company number.');
      return;
    }
    setGraphLoading(true);
    setGraphError(null);
    setGraphResult(null);
    try {
      graphAbortRef.current?.abort();
      const controller = new AbortController();
      graphAbortRef.current = controller;
      const res = await getCHHopGraph(company, graphHops, undefined, controller.signal);
      setGraphResult(res);
    } catch (e: unknown) {
      setGraphError(e instanceof Error ? e.message : 'Could not load graph.');
    } finally {
      setGraphLoading(false);
    }
  }, [graphCompany, graphHops]);

  const graphData = useMemo(() => {
    if (!graphResult) {
      return { nodes: [], links: [] };
    }
    const nodes = graphResult.nodes.map((n) => ({
      ...n,
      val: n.id === graphResult.root.id ? 11 : n.label === 'Company' ? 8 : 6,
      color: n.id === graphResult.root.id ? '#16a34a' : n.label === 'Company' ? '#2563eb' : '#7c3aed',
    }));
    const links = graphResult.edges.map((e, idx) => ({
      id: `${e.source}-${e.target}-${e.type}-${idx}`,
      source: e.source,
      target: e.target,
      type: e.type,
      color: e.type === 'PSC_OF' ? '#d97706' : '#64748b',
    }));
    return { nodes, links };
  }, [graphResult]);

  // Fit view after the force sim stops — ref is only set once ForceGraph2D mounts (lazy + Suspense),
  // so useEffect(graphResult) often ran while graphRef was still null and never re-ran.
  const handleGraphEngineStop = useCallback(() => {
    requestAnimationFrame(() => {
      try {
        graphRef.current?.zoomToFit(400, 70);
      } catch {
        // Canvas not ready yet.
      }
    });
  }, []);

  // Re-fit when the container width changes (sidebar / window resize).
  useEffect(() => {
    if (!graphResult) return;
    const t = window.setTimeout(() => {
      try {
        graphRef.current?.zoomToFit(400, 70);
      } catch {
        /* ignore */
      }
    }, 100);
    return () => window.clearTimeout(t);
  }, [graphResult, graphSize.width]);

  return (
    <div className="flex h-full">
      <div className="flex-1 flex flex-col h-full">
        <div className="flex-1 overflow-hidden relative">
          <div className="h-full overflow-y-auto p-6 sm:p-10 custom-scrollbar">
            <div className="max-w-2xl mx-auto">
              <div className="p-4 sm:p-6 rounded-xl bg-surface-card border border-slate-200 shadow-sm">
                <h2 className="text-lg font-bold text-ink mb-4 flex items-center gap-2">
                  <Building2 className="w-5 h-5 text-accent" />
                  Companies House Pipeline
                </h2>
                <p className="text-sm text-ink-muted mb-6">
                  Fetch filings, officers, and PSC data from Companies House. Resolve by company number, officer ID, or name.
                  API key configured in Settings.
                </p>

                {/* Search type dropdown */}
                <div className="mb-4">
                  <label className="block text-[10px] font-bold uppercase tracking-widest text-ink-muted mb-1">
                    Search type
                  </label>
                  <div className="relative">
                    <select
                      value={searchType}
                      onChange={(e) => setSearchType(e.target.value as SearchType)}
                      className="w-full px-4 py-2.5 bg-surface-muted border border-slate-200 rounded-xl text-ink text-sm focus:outline-none focus:ring-2 focus:ring-accent/50 appearance-none pr-10"
                    >
                      {SEARCH_TYPE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-muted pointer-events-none" />
                  </div>
                </div>

                {/* Search value */}
                <div className="mb-6">
                  <label className="block text-[10px] font-bold uppercase tracking-widest text-ink-muted mb-1">
                    {searchType === 'company_number' && 'Company number(s)'}
                    {searchType === 'officer_id' && 'Officer ID'}
                    {searchType === 'name' && 'Name'}
                  </label>
                  <input
                    type="text"
                    value={searchValue}
                    onChange={(e) => setSearchValue(e.target.value)}
                    placeholder={
                      searchType === 'company_number'
                        ? 'e.g. 12345678 or 12345678, 87654321'
                        : searchType === 'officer_id'
                        ? 'e.g. JaAPovia7sLF0HHx-Erk9eCiDqQ'
                        : 'e.g. John Smith or Acme Ltd'
                    }
                    className="w-full px-4 py-2.5 bg-surface-muted border border-slate-200 rounded-xl text-ink text-sm focus:outline-none focus:ring-2 focus:ring-accent/50 placeholder-ink-subtle"
                  />
                </div>

                {/* Actions */}
                <div className="flex flex-wrap items-center gap-4">
                  <button
                    onClick={handleRun}
                    disabled={isLoading}
                    className="flex items-center gap-2 bg-accent hover:bg-accent-hover px-4 py-2.5 rounded-xl text-white text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isLoading ? (
                      <Spinner />
                    ) : (
                      <Play className="w-4 h-4" />
                    )}
                    Run pipeline
                  </button>
                  {result?.job_id && (
                    <a
                      href={getCHDownloadUrl(result.job_id)}
                      download={`ch_pipeline_${result.job_id}.zip`}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-200 hover:bg-slate-300 text-ink text-sm font-semibold transition-colors"
                    >
                      <Download className="w-4 h-4" />
                      Download CSVs
                    </a>
                  )}
                </div>

                {/* Error */}
                {error && (
                  <div className="mt-4 p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-sm">
                    {error}
                  </div>
                )}

                {/* Summary */}
                {result && !error && (
                  <div className="mt-6 p-4 rounded-xl bg-surface-muted border border-slate-200">
                    <h3 className="text-sm font-bold text-ink mb-2">Summary</h3>
                    <dl className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-sm">
                      {result.companies_processed != null && (
                        <div>
                          <dt className="text-ink-muted">Companies</dt>
                          <dd className="font-mono text-ink">{result.companies_processed}</dd>
                        </div>
                      )}
                      {result.filings != null && (
                        <div>
                          <dt className="text-ink-muted">Filings</dt>
                          <dd className="font-mono text-ink">{result.filings}</dd>
                        </div>
                      )}
                      {result.officers != null && (
                        <div>
                          <dt className="text-ink-muted">Officers</dt>
                          <dd className="font-mono text-ink">{result.officers}</dd>
                        </div>
                      )}
                      {result.psc != null && (
                        <div>
                          <dt className="text-ink-muted">PSC</dt>
                          <dd className="font-mono text-ink">{result.psc}</dd>
                        </div>
                      )}
                      {result.officer_failures != null && result.officer_failures > 0 && (
                        <div>
                          <dt className="text-ink-muted">Officer failures</dt>
                          <dd className="font-mono text-amber-600">{result.officer_failures}</dd>
                        </div>
                      )}
                    </dl>
                    {result.files && result.files.length > 0 && (
                      <p className="mt-2 text-xs text-ink-muted">
                        Files: {result.files.join(', ')}
                      </p>
                    )}
                  </div>
                )}

                {/* Link to History tab for past runs */}
                {jobs.length > 0 && (
                  <p className="mt-6 text-xs text-ink-muted">
                    {jobs.length} run(s) saved. View and download from the History sub-tab.
                  </p>
                )}
              </div>

              {/* Filing PDFs — list metadata then download selected (Companies House Document API) */}
              <div className="mt-10 p-4 sm:p-6 rounded-xl bg-surface-card border border-slate-200 shadow-sm">
                <h2 className="text-lg font-bold text-ink mb-2 flex items-center gap-2">
                  <FileText className="w-5 h-5 text-accent" />
                  Filing documents (PDF)
                </h2>
                <p className="text-sm text-ink-muted mb-4">
                  List filings for one company, optionally filter by calendar year, then tick rows with a PDF and download.
                  Uses the same API key as Settings.
                </p>

                <div className="mb-3">
                  <label className="block text-[10px] font-bold uppercase tracking-widest text-ink-muted mb-1">
                    Company number
                  </label>
                  <input
                    type="text"
                    value={docCompany}
                    onChange={(e) => setDocCompany(e.target.value)}
                    placeholder="e.g. 12345678"
                    className="w-full px-4 py-2.5 bg-surface-muted border border-slate-200 rounded-xl text-ink text-sm focus:outline-none focus:ring-2 focus:ring-accent/50"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-widest text-ink-muted mb-1">
                      Year from (optional)
                    </label>
                    <input
                      type="text"
                      inputMode="numeric"
                      value={docYearFrom}
                      onChange={(e) => setDocYearFrom(e.target.value)}
                      placeholder="e.g. 2020"
                      className="w-full px-4 py-2.5 bg-surface-muted border border-slate-200 rounded-xl text-ink text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-widest text-ink-muted mb-1">
                      Year to (optional)
                    </label>
                    <input
                      type="text"
                      inputMode="numeric"
                      value={docYearTo}
                      onChange={(e) => setDocYearTo(e.target.value)}
                      placeholder="e.g. 2024"
                      className="w-full px-4 py-2.5 bg-surface-muted border border-slate-200 rounded-xl text-ink text-sm"
                    />
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-3 mb-4">
                  <button
                    type="button"
                    onClick={handleListFilings}
                    disabled={docListLoading}
                    className="flex items-center gap-2 bg-slate-200 hover:bg-slate-300 px-4 py-2.5 rounded-xl text-ink text-sm font-semibold disabled:opacity-50"
                  >
                    {docListLoading ? <Spinner /> : null}
                    List filings
                  </button>
                  <button
                    type="button"
                    onClick={selectAllWithPdf}
                    disabled={docFilings.length === 0}
                    className="text-sm text-accent font-medium hover:underline disabled:opacity-40"
                  >
                    Select all with PDF
                  </button>
                </div>

                {docError && (
                  <div className="mb-4 p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-sm">
                    {docError}
                  </div>
                )}

                {docFilings.length > 0 && (
                  <div className="mb-4 max-h-64 overflow-y-auto border border-slate-200 rounded-xl">
                    <table className="w-full text-xs text-left">
                      <thead className="bg-slate-100 sticky top-0">
                        <tr>
                          <th className="p-2 w-8" />
                          <th className="p-2">Date</th>
                          <th className="p-2">Type</th>
                          <th className="p-2 hidden sm:table-cell">Description</th>
                          <th className="p-2">PDF</th>
                        </tr>
                      </thead>
                      <tbody>
                        {docFilings.map((f, i) => {
                          const tid = f.transaction_id || '';
                          const canPick = f.has_document && tid;
                          const checked = tid && docSelected.has(tid);
                          return (
                            <tr key={`${tid}-${i}`} className="border-t border-slate-100">
                              <td className="p-2 align-top">
                                <input
                                  type="checkbox"
                                  disabled={!canPick}
                                  checked={!!checked}
                                  onChange={() => toggleDocRow(f.transaction_id, f.has_document)}
                                  className="rounded border-slate-300"
                                />
                              </td>
                              <td className="p-2 align-top font-mono text-ink">{f.date || '—'}</td>
                              <td className="p-2 align-top text-ink">{f.filing_type || '—'}</td>
                              <td className="p-2 align-top text-ink-muted hidden sm:table-cell max-w-[200px] truncate">
                                {f.description || '—'}
                              </td>
                              <td className="p-2 align-top">{f.has_document ? 'Yes' : '—'}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-4">
                  <button
                    type="button"
                    onClick={handleDownloadPdfs}
                    disabled={docDownLoading || docSelected.size === 0}
                    className="flex items-center gap-2 bg-accent hover:bg-accent-hover px-4 py-2.5 rounded-xl text-white text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {docDownLoading ? <Spinner /> : <Download className="w-4 h-4" />}
                    Download selected PDFs
                  </button>
                  {docResult?.job_id && (
                    <a
                      href={getCHDownloadUrl(docResult.job_id)}
                      download={`ch_documents_${docResult.job_id}.zip`}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-200 hover:bg-slate-300 text-ink text-sm font-semibold transition-colors"
                    >
                      <Download className="w-4 h-4" />
                      Download ZIP
                    </a>
                  )}
                </div>

                {docResult && !docError && (
                  <p className="mt-3 text-xs text-ink-muted">
                    Saved {docResult.downloaded ?? 0} PDF(s)
                    {docResult.failed != null && docResult.failed > 0 && (
                      <span className="text-amber-700"> · {docResult.failed} failed (see download_failures.json in ZIP)</span>
                    )}
                    .
                  </p>
                )}
              </div>

              {/* Relationship map — variable hop company network from Neo4j */}
              <div className="mt-10 p-4 sm:p-6 rounded-xl bg-surface-card border border-slate-200 shadow-sm">
                <h2 className="text-lg font-bold text-ink mb-2 flex items-center gap-2">
                  <Share2 className="w-5 h-5 text-accent" />
                  Relationship map (hops)
                </h2>
                <p className="text-sm text-ink-muted mb-4">
                  Explore directors and PSC links from one company across multiple hops. Import the CH pipeline CSVs into Neo4j
                  (Company / Person nodes, OFFICER_OF / PSC_OF relationships) so this map has data.
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
                  <div className="sm:col-span-2">
                    <label className="block text-[10px] font-bold uppercase tracking-widest text-ink-muted mb-1">
                      Company number
                    </label>
                    <input
                      type="text"
                      value={graphCompany}
                      onChange={(e) => setGraphCompany(e.target.value)}
                      placeholder="e.g. 12345678"
                      className="w-full px-4 py-2.5 bg-surface-muted border border-slate-200 rounded-xl text-ink text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-widest text-ink-muted mb-1">
                      Hops
                    </label>
                    <select
                      value={graphHops}
                      onChange={(e) => setGraphHops(Number.parseInt(e.target.value, 10))}
                      className="w-full px-4 py-2.5 bg-surface-muted border border-slate-200 rounded-xl text-ink text-sm"
                    >
                      {[1, 2, 3, 4].map((h) => (
                        <option key={h} value={h}>
                          {h}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="flex items-center gap-3 mb-4">
                  <button
                    type="button"
                    onClick={handleLoadGraph}
                    disabled={graphLoading}
                    className="flex items-center gap-2 bg-accent hover:bg-accent-hover px-4 py-2.5 rounded-xl text-white text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {graphLoading ? <Spinner /> : <Play className="w-4 h-4" />}
                    Load map
                  </button>
                  {graphResult && (
                    <span className="text-xs text-ink-muted">
                      {graphResult.nodes.length} nodes · {graphResult.edges.length} edges
                    </span>
                  )}
                </div>

                {graphError && (
                  <div className="mb-4 p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-sm">
                    {graphError}
                  </div>
                )}

                <div ref={graphWrapRef} className="w-full h-[420px] rounded-xl border border-slate-200 bg-surface-muted overflow-hidden">
                  {graphResult ? (
                    <Suspense
                      fallback={
                        <div className="h-full w-full flex items-center justify-center text-sm text-ink-muted">
                          <Spinner />
                        </div>
                      }
                    >
                      <ForceGraph2D
                        key={`${graphResult.root.id}-${graphResult.nodes.length}-${graphResult.edges.length}`}
                        ref={graphRef}
                        width={graphSize.width}
                        height={graphSize.height}
                        graphData={graphData}
                        cooldownTicks={80}
                        onEngineStop={handleGraphEngineStop}
                        linkDirectionalParticles={0}
                        nodeLabel={(n: any) => `${n.name} (${n.label})${n.company_number ? `\n${n.company_number}` : ''}`}
                        nodeRelSize={6}
                        nodeVal={(n: any) => n.val}
                        nodeColor={(n: any) => n.color}
                        linkColor={(l: any) => l.color}
                        linkWidth={1.4}
                        nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
                          const label = node.name || node.id;
                          const size = node.val || 6;
                          ctx.beginPath();
                          ctx.arc(node.x, node.y, size, 0, 2 * Math.PI, false);
                          ctx.fillStyle = node.color || '#334155';
                          ctx.fill();
                          const fontSize = Math.max(10 / globalScale, 3);
                          ctx.font = `${fontSize}px Sans-Serif`;
                          ctx.textAlign = 'center';
                          ctx.textBaseline = 'top';
                          ctx.fillStyle = '#1e293b';
                          ctx.fillText(label, node.x, node.y + size + 1);
                        }}
                      />
                    </Suspense>
                  ) : (
                    <div className="h-full w-full flex items-center justify-center text-sm text-ink-muted">
                      Enter company number and load map.
                    </div>
                  )}
                </div>

                {graphResult && graphResult.edges.length === 0 && (
                  <p className="mt-3 text-xs text-ink-muted">
                    No edges in range — either no officer/PSC relationships in Neo4j for this company, or hops are too shallow.
                  </p>
                )}

                {graphResult?.truncated && (graphResult.truncated.nodes || graphResult.truncated.edges) && (
                  <p className="mt-3 text-xs text-amber-700">
                    Graph was truncated for performance. Reduce hops for a smaller view.
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
