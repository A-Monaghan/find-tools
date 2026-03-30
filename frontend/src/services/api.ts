/**
 * API client for FIND Tools (RAG) backend
 */

import {
  DocumentSummary,
  DocumentDetail,
  DocumentUploadResponse,
  QueryRequest,
  QueryResponse,
  Conversation,
  AvailableModelsResponse,
  WorkspaceSummary,
  GlobalSearchHit,
} from '../types';

// In browser: VITE_API_BASE_URL when set to the *backend* URL, else same-origin /api (nginx proxy).
// If VITE is wrongly set to the SPA origin (no /api path), POSTs hit nginx static → 405 Not Allowed.
export function getApiBase(): string {
  if (typeof window !== 'undefined') {
    const raw = import.meta.env.VITE_API_BASE_URL;
    if (!raw) return '/api';
    const base = String(raw).replace(/\/$/, '');
    try {
      const u = new URL(base);
      const path = u.pathname.replace(/\/$/, '') || '';
      if (u.origin === window.location.origin && path === '') {
        return '/api';
      }
    } catch {
      /* relative or invalid; use as-is */
    }
    return base;
  }
  return (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '') || 'http://localhost:8000';
}

class APIError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'APIError';
  }
}

const cacheStore = new Map<string, { expiresAt: number; value: unknown }>();

function cacheGet<T>(key: string): T | null {
  const hit = cacheStore.get(key);
  if (!hit) return null;
  if (Date.now() > hit.expiresAt) {
    cacheStore.delete(key);
    return null;
  }
  return hit.value as T;
}

function cacheSet<T>(key: string, value: T, ttlMs: number): T {
  cacheStore.set(key, { expiresAt: Date.now() + ttlMs, value });
  return value;
}

function toErrorMessage(response: Response, raw: string): string {
  if (response.status === 502) {
    return 'Backend unreachable (502). Is the backend container running? Run: docker-compose ps';
  }
  const body = (raw || '').trim();
  if (!body) return response.statusText || `HTTP ${response.status}`;
  if (body.startsWith('<')) return response.statusText || `HTTP ${response.status}`;
  try {
    const json = JSON.parse(body) as { detail?: string; error?: string; message?: string };
    return json.detail || json.error || json.message || body;
  } catch {
    return body;
  }
}

async function fetchJSON<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const base = getApiBase();
  const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  const url = base ? `${base}${path}` : path;
  
  const response = await fetch(url, {
    ...options,
    cache: 'no-store', // Prevent stale responses on refresh (avoids stuck state)
    headers: {
      'Accept': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    const raw = await response.text();
    const message = toErrorMessage(response, raw);
    throw new APIError(response.status, message);
  }

  return response.json();
}

// ============== Documents API ==============

export async function uploadDocument(
  file: File,
  onProgress?: (progress: number) => void,
  workspaceId?: string | null
): Promise<DocumentUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  if (workspaceId) {
    formData.append('workspace_id', workspaceId);
  }

  const uploadUrl = `${getApiBase()}/documents/upload`;
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const timeoutMs = 600_000; // 10 min for large PDFs

    xhr.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress((event.loaded / event.total) * 100);
      }
    });

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        const raw = xhr.responseText || xhr.statusText;
        const msg = xhr.status === 502
          ? 'Backend unreachable (502). Run: docker-compose ps and docker-compose logs backend'
          : (raw.startsWith('<') ? xhr.statusText : raw);
        reject(new APIError(xhr.status, msg));
      }
    });

    xhr.addEventListener('error', () => {
      reject(new APIError(0, `Network error: cannot reach ${uploadUrl}. Is the backend running? (docker-compose ps)`));
    });

    xhr.addEventListener('timeout', () => {
      reject(new APIError(0, `Upload timed out after ${timeoutMs / 1000}s. Try a smaller file or check backend.`));
    });

    xhr.open('POST', uploadUrl);
    xhr.timeout = timeoutMs;
    xhr.send(formData);
  });
}

export async function listDocuments(workspaceId?: string | null): Promise<DocumentSummary[]> {
  const q =
    workspaceId != null && workspaceId !== ''
      ? `?workspace_id=${encodeURIComponent(workspaceId)}`
      : '';
  return fetchJSON(`/documents/${q}`);
}

export async function listWorkspaces(): Promise<WorkspaceSummary[]> {
  return fetchJSON('/workspaces/');
}

export async function createWorkspace(name: string): Promise<WorkspaceSummary> {
  return fetchJSON('/workspaces/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
}

export async function searchCorpus(
  query: string,
  workspaceId?: string | null,
  signal?: AbortSignal
): Promise<GlobalSearchHit[]> {
  const params = new URLSearchParams({ q: query });
  if (workspaceId) {
    params.set('workspace_id', workspaceId);
  }
  const key = `search:${params.toString()}`;
  const cached = cacheGet<GlobalSearchHit[]>(key);
  if (cached) return cached;
  const result = await fetchJSON<GlobalSearchHit[]>(`/documents/search?${params.toString()}`, { signal });
  return cacheSet(key, result, 15_000);
}

export async function getDocument(id: string): Promise<DocumentDetail> {
  return fetchJSON(`/documents/${id}`);
}

export async function getDocumentChunks(
  documentId: string,
  pageSize = 3
): Promise<
  { text: string; start_page: number; end_page: number; chunk_strategy?: string | null }[]
> {
  const res = await fetchJSON<{
    chunks: {
      text_preview: string;
      start_page: number;
      end_page: number;
      chunk_strategy?: string | null;
    }[];
  }>(`/documents/${documentId}/chunks?page_size=${pageSize}&page=1`);
  return (res.chunks || []).map((c) => ({
    text: c.text_preview,
    start_page: c.start_page,
    end_page: c.end_page,
    chunk_strategy: c.chunk_strategy,
  }));
}

export async function deleteDocument(id: string): Promise<void> {
  await fetchJSON(`/documents/${id}`, { method: 'DELETE' });
}

export async function patchDocument(
  id: string,
  body: { workspace_id?: string | null; original_name?: string }
): Promise<DocumentDetail> {
  return fetchJSON(`/documents/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export async function importDocumentFromUrl(url: string): Promise<DocumentUploadResponse> {
  return fetchJSON('/documents/import-url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
}

export async function extractEntitiesFromDocument(
  documentId: string,
  options: { source?: string; model?: string; extraction_method?: string; push_to_neo4j?: boolean }
): Promise<{ entities: { id: string; name: string; label: string }[]; relationships: { id: string; source: string; target: string; type: string }[] }> {
  return fetchJSON(`/documents/${documentId}/extract-entities`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      source: options.source ?? 'full_text',
      model: options.model ?? 'openai/gpt-4o-mini',  // Shared with unified-app (see shared/llm-models.json)
      extraction_method: options.extraction_method ?? 'quality',
      push_to_neo4j: options.push_to_neo4j ?? false,
    }),
  });
}

// ============== Chat API ==============

export async function queryDocuments(
  request: QueryRequest,
  signal?: AbortSignal
): Promise<QueryResponse> {
  return fetchJSON('/chat/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    signal,
  });
}

export async function getAvailableModels(): Promise<AvailableModelsResponse> {
  return fetchJSON('/chat/models');
}

export async function createConversation(documentId?: string): Promise<{ id: string }> {
  const params = documentId ? `?document_id=${documentId}` : '';
  return fetchJSON(`/chat/conversations${params}`, { method: 'POST' });
}

export async function getConversations(documentId?: string): Promise<Conversation[]> {
  const params = documentId ? `?document_id=${documentId}` : '';
  return fetchJSON(`/chat/conversations${params}`);
}

export async function deleteConversation(id: string): Promise<void> {
  await fetchJSON(`/chat/conversations/${id}`, { method: 'DELETE' });
}

// ============== Logs API ==============

export async function getQueryLogs(limit: number = 100): Promise<Record<string, unknown>[]> {
  return fetchJSON(`/logs/queries?limit=${limit}`);
}

// ============== Health API ==============

export async function getHealth(): Promise<{ status: string }> {
  return fetchJSON('/health');
}

// ============== Companies House API ==============

export interface CHRunResult {
  status: string;
  job_id?: string;
  companies_processed?: number;
  filings?: number;
  officers?: number;
  psc?: number;
  officer_failures?: number;
  documents_downloaded?: number;
  documents_failed?: number;
  files?: string[];
  out_dir?: string;
  error?: string;
}

export interface CHJob {
  job_id: string;
  created_at: number;
  search_type: string;
  search_value: string;
  job_kind?: string;
  companies_processed?: number;
  filings?: number;
  officers?: number;
  psc?: number;
  documents_downloaded?: number;
  documents_failed?: number;
}

/** Filing row from POST /ch/filings/list (metadata only). */
export interface CHFilingListItem {
  transaction_id: string | null;
  date: string | null;
  filing_type: string | null;
  description: string | null;
  category: string | null;
  has_document: boolean;
  document_id: string | null;
}

export interface CHGraphNode {
  id: string;
  label: string;
  name: string;
  company_number?: string | null;
  person_id?: string | null;
}

export interface CHGraphEdge {
  source: string;
  target: string;
  type: string;
}

export interface CHHopGraphResponse {
  root: CHGraphNode;
  hops: number;
  nodes: CHGraphNode[];
  edges: CHGraphEdge[];
  truncated: {
    nodes: boolean;
    edges: boolean;
  };
}

export async function listCHFilings(
  companyNumber: string,
  opts: { yearFrom?: number | null; yearTo?: number | null; apiKey?: string | null },
  signal?: AbortSignal
): Promise<{ company_number: string; filings: CHFilingListItem[] }> {
  const body = {
    company_number: companyNumber.trim(),
    year_from: opts.yearFrom ?? null,
    year_to: opts.yearTo ?? null,
    api_key: opts.apiKey || null,
  };
  const key = `ch_filings:${JSON.stringify(body)}`;
  const cached = cacheGet<{ company_number: string; filings: CHFilingListItem[] }>(key);
  if (cached) return cached;
  const result = await fetchJSON<{ company_number: string; filings: CHFilingListItem[] }>('/ch/filings/list', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });
  return cacheSet(key, result, 60_000);
}

export async function downloadCHDocuments(
  companyNumber: string,
  transactionIds: string[],
  apiKey?: string | null
): Promise<CHRunResult> {
  return fetchJSON('/ch/documents/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      company_number: companyNumber.trim(),
      transaction_ids: transactionIds,
      api_key: apiKey || null,
    }),
  });
}

export async function getCHHopGraph(
  companyNumber: string,
  hops: number,
  opts?: { maxNodes?: number; maxEdges?: number },
  signal?: AbortSignal
): Promise<CHHopGraphResponse> {
  const body = {
    company_number: companyNumber.trim(),
    hops,
    max_nodes: opts?.maxNodes ?? 400,
    max_edges: opts?.maxEdges ?? 1200,
  };
  const key = `ch_graph:${JSON.stringify(body)}`;
  const cached = cacheGet<CHHopGraphResponse>(key);
  if (cached) return cached;
  const result = await fetchJSON<CHHopGraphResponse>('/ch/graph/hops', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });
  return cacheSet(key, result, 60_000);
}

export async function runCHPipeline(
  searchType: 'company_number' | 'officer_id' | 'name',
  searchValue: string,
  apiKey?: string | null
): Promise<CHRunResult> {
  return fetchJSON('/ch/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      search_type: searchType,
      search_value: searchValue,
      api_key: apiKey || null,
    }),
  });
}

export async function listCHJobs(): Promise<{ jobs: CHJob[] }> {
  const key = 'ch_jobs';
  const cached = cacheGet<{ jobs: CHJob[] }>(key);
  if (cached) return cached;
  const result = await fetchJSON<{ jobs: CHJob[] }>('/ch/jobs');
  return cacheSet(key, result, 10_000);
}

export async function deleteCHJob(jobId: string): Promise<void> {
  await fetchJSON(`/ch/jobs/${jobId}`, { method: 'DELETE' });
}

/** Returns the download URL for a job (or latest if jobId omitted). */
export function getCHDownloadUrl(jobId?: string): string {
  const base =
    typeof window !== 'undefined' ? getApiBase() : (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '') || 'http://localhost:8000';
  return jobId ? `${base}/ch/download/${jobId}` : `${base}/ch/download`;
}

// --- Name / DOB screening (OpenSanctions, Aleph, Sayari) — keys on server only ---

export type ScreeningSource = 'opensanctions' | 'aleph' | 'sayari';

export interface ScreeningStatusResponse {
  opensanctions: boolean;
  aleph: boolean;
  sayari: boolean;
  aleph_api_base: string;
  sayari_api_base: string;
}

export interface NameScreeningRequest {
  name: string;
  dob?: string | null;
  sources: ScreeningSource[];
  /** Browser or automation — overrides server env when non-empty */
  opensanctions_api_key?: string | null;
  aleph_api_key?: string | null;
  aleph_api_base?: string | null;
  sayari_client_id?: string | null;
  sayari_client_secret?: string | null;
  sayari_api_base?: string | null;
}

/** Loose result shape — each upstream returns ok, matches[], optional error */
export type ScreeningNameSearchResponse = {
  query: { name: string; dob: string | null };
  opensanctions: Record<string, unknown> | null;
  aleph: Record<string, unknown> | null;
  sayari: Record<string, unknown> | null;
};

export async function getScreeningStatus(): Promise<ScreeningStatusResponse> {
  return fetchJSON<ScreeningStatusResponse>('/screening/status');
}

export async function runNameScreening(
  body: NameScreeningRequest
): Promise<ScreeningNameSearchResponse> {
  const payload: Record<string, unknown> = {
    name: body.name,
    dob: body.dob ?? null,
    sources: body.sources,
  };
  const trimOrOmit = (k: keyof NameScreeningRequest) => {
    const v = body[k];
    if (typeof v === 'string' && v.trim()) payload[k as string] = v.trim();
  };
  trimOrOmit('opensanctions_api_key');
  trimOrOmit('aleph_api_key');
  trimOrOmit('aleph_api_base');
  trimOrOmit('sayari_client_id');
  trimOrOmit('sayari_client_secret');
  trimOrOmit('sayari_api_base');

  return fetchJSON<ScreeningNameSearchResponse>('/screening/name-search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}