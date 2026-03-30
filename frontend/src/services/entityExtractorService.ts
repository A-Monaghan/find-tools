/**
 * Entity Extractor (Text Body Extractor) API client.
 * Dev: Vite proxies /ee → Text Body Extractor (services/text-body-extractor, default :5001).
 * Prod: nginx has no /ee unless you add it — set VITE_ENTITY_EXTRACTOR_URL to a public extractor URL.
 */
const UNCONFIGURED_MSG =
  'Entity Extractor is not configured for this deployment. Set VITE_ENTITY_EXTRACTOR_URL to your Text Body Extractor service URL.';

const UNREACHABLE_MSG = `Entity Extractor backend not reachable. Start it: cd services/text-body-extractor && ./start_backend.sh`;

function getEeBase(): string {
  const v = import.meta.env.VITE_ENTITY_EXTRACTOR_URL;
  if (v != null && String(v).trim() !== '') return String(v).replace(/\/$/, '');
  if (import.meta.env.DEV) return '/ee';
  return '';
}

/** Text Body Extractor paths always start with /api/... */
function eeUrl(path: string): string {
  const base = getEeBase();
  if (!base) throw new Error(UNCONFIGURED_MSG);
  const p = path.startsWith('/') ? path : `/${path}`;
  return `${base}${p}`;
}

async function parseErrorMessage(res: Response): Promise<string> {
  try {
    const text = await res.text();
    if (!text) return res.statusText || `HTTP ${res.status}`;
    try {
      const json = JSON.parse(text) as { detail?: string; error?: string; message?: string };
      return json.detail || json.error || json.message || text;
    } catch {
      return text;
    }
  } catch {
    return res.statusText || `HTTP ${res.status}`;
  }
}

async function safeFetch(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (e: any) {
    if (e?.message === 'Failed to fetch' || e?.name === 'TypeError') {
      throw new Error(UNREACHABLE_MSG);
    }
    throw e;
  }
}

export interface RawEntity {
  name: string;
  label: string;
}

export interface RawRelationship {
  source: string;
  target: string;
  type: string;
}

export interface PromptDefaults {
  system_prompt: string;
  user_prompt_template: string;
  content_placeholder: string;
}

export interface AnalyzePayload {
  model_type: 'openrouter' | 'openai' | 'ollama';
  api_key?: string;
  openai_api_key?: string;
  openrouter_model?: string;
  openai_model?: string;
  ollama_model?: string;
  url?: string;
  text?: string;
  input_mode: 'url' | 'text';
  two_pass?: boolean;
  system_prompt?: string | null;
  user_prompt_template?: string | null;
  chunking_method?: string | null;
  extraction_method?: string | null;
}

export interface AnalyzeResponse {
  success: boolean;
  data: { entities: RawEntity[]; relationships: RawRelationship[] };
  extracted_text?: string | null;
}

export async function analyzeWithBackend(payload: AnalyzePayload): Promise<AnalyzeResponse> {
  const res = await safeFetch(eeUrl('/api/analyze'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseErrorMessage(res));
  return (await res.json()) as AnalyzeResponse;
}

export async function analyzeWithBackendStreaming(
  payload: AnalyzePayload,
  onProgress: (p: { message?: string }) => void
): Promise<AnalyzeResponse> {
  let res = await safeFetch(eeUrl('/api/analyze-stream'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (res.status === 404) return analyzeWithBackend(payload);
  if (!res.ok) throw new Error(await parseErrorMessage(res));
  const reader = res.body?.getReader();
  if (!reader) throw new Error('No response body');
  const decoder = new TextDecoder();
  let buffer = '';
  let finalResult: AnalyzeResponse | null = null;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const data = JSON.parse(line.slice(6));
          if (data.type === 'result') {
            finalResult = {
              success: data.success,
              data: data.data,
              extracted_text: data.extracted_text,
            };
          } else if (data.type === 'error') {
            throw new Error(data.detail ?? 'Extraction failed');
          } else {
            onProgress(data);
          }
        } catch (e) {
          if (e instanceof Error && e.message !== 'Extraction failed') {
            /* JSON parse error */
          }
        }
      }
    }
  }
  if (!finalResult) throw new Error('No result received');
  return finalResult;
}

export async function fetchPromptDefaults(): Promise<PromptDefaults> {
  const res = await safeFetch(eeUrl('/api/prompt-defaults'));
  if (!res.ok) throw new Error(UNREACHABLE_MSG);
  return (await res.json()) as Promise<PromptDefaults>;
}

export async function fetchNeo4jStatus(): Promise<{ connected: boolean; error?: string }> {
  const res = await safeFetch(eeUrl('/api/neo4j-status'));
  return (await res.json()) as { connected: boolean; error?: string };
}

export interface Neo4jConnection {
  uri?: string;
  username?: string;
  password?: string;
}

export async function pushToNeo4j(
  entities: { id: string; name: string; label: string }[],
  relationships: { id: string; source: string; target: string; type: string }[],
  connection?: Neo4jConnection
): Promise<{ success: boolean; nodes_created: number; relationships_created: number }> {
  const body: Record<string, unknown> = { entities, relationships };
  if (connection?.uri) body.neo4j_uri = connection.uri;
  if (connection?.username) body.neo4j_username = connection.username;
  if (connection?.password) body.neo4j_password = connection.password;
  const res = await safeFetch(eeUrl('/api/push-to-neo4j'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await parseErrorMessage(res));
  return (await res.json()) as { success: boolean; nodes_created: number; relationships_created: number };
}
