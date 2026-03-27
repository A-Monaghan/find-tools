/**
 * TypeScript type definitions for FIND Tools frontend
 */

// ============== Document Types ==============

export interface DocumentSummary {
  id: string;
  filename: string;
  original_name: string;
  total_pages: number;
  chunk_count: number;
  upload_date: string;
  status: 'processing' | 'indexed' | 'error';
  error_message?: string | null;
  workspace_id?: string | null;
  ingest_stage?: string | null;
  chunk_preset_id?: string | null;
}

export interface DocumentDetail {
  id: string;
  filename: string;
  original_name: string;
  file_size: number;
  total_pages: number;
  chunk_count: number;
  upload_date: string;
  status: 'processing' | 'indexed' | 'error';
  error_message?: string | null;
}

export interface DocumentUploadResponse {
  id: string;
  filename: string;
  status: 'processing' | 'indexed' | 'error';
  total_pages: number;
  upload_date: string;
  message: string;
}

// ============== Chat Types ==============

export interface Citation {
  document_id: string;
  document_name: string;
  chunk_id: string;
  start_page: number;
  end_page: number;
  evidence_quote: string;
  relevance_score: number;
}

export interface RetrievedChunk {
  chunk_id: string;
  document_id: string;
  document_name: string;
  text: string;
  start_page: number;
  end_page: number;
  score: number;
}

export interface RetrievalTraceChunk {
  chunk_id: string;
  dense_rank: number;
  bm25_rank: number;
  fused_score?: number | null;
  dense_score?: number | null;
}

export interface RetrievalTrace {
  hyde_used: boolean;
  fusion_enabled: boolean;
  fusion_alpha?: number | null;
  rrf_k?: number | null;
  mode: string;
  crag_action?: string | null;
  web_augmented: boolean;
  chunks: RetrievalTraceChunk[];
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  citations?: Citation[];
  retrieved_chunks?: RetrievedChunk[];
  retrieval_trace?: RetrievalTrace | null;
}

export interface QueryRequest {
  query: string;
  document_id?: string | null;
  conversation_id?: string | null;
  model?: string | null;
  system_prompt?: string;
}

export interface QueryResponse {
  answer: string;
  citations: Citation[];
  retrieved_chunks: RetrievedChunk[];
  conversation_id: string;
  model_used: string;
  latency_ms: number;
  token_count_prompt: number;
  token_count_response: number;
  retrieval_trace?: RetrievalTrace | null;
}

export interface Conversation {
  id: string;
  document_id: string | null;
  created_at: string;
  updated_at: string;
  messages: Message[];
}

// ============== UI Types ==============

export interface UploadProgress {
  file: File;
  progress: number;
  status: 'pending' | 'uploading' | 'processing' | 'completed' | 'error';
  error?: string;
}

export interface AppState {
  selectedDocument: DocumentSummary | null;
  searchMode: 'single' | 'all';
  isSidebarOpen: boolean;
  isCitationPanelOpen: boolean;
}

export interface AvailableModel {
  id: string;
  name: string;
  provider: string;
}

export interface AvailableModelsResponse {
  models: AvailableModel[];
  default_model: string;
  /** Server-configured OpenRouter id for fast/cheap draft queries */
  fast_model: string;
  active_provider: string;
}

export interface WorkspaceSummary {
  id: string;
  name: string;
  created_at: string;
}

export interface GlobalSearchHit {
  chunk_id: string;
  document_id: string;
  document_name: string;
  start_page: number;
  end_page: number;
  snippet: string;
  chunk_strategy?: string | null;
}