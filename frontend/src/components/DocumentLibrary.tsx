/**
 * Document Library Component
 *
 * Inspired by Danswer's connector-style document management.
 * Shows uploaded documents with status, allows selection and upload.
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { FileText, Trash2, Upload, Loader2, CheckCircle2, AlertCircle, BookOpen, Eye, Link2, Network, RefreshCw, FolderOpen, Plus } from 'lucide-react';
import { DocumentSummary, AvailableModel, WorkspaceSummary, GlobalSearchHit } from '../types';
import {
  uploadDocument,
  deleteDocument,
  listDocuments,
  getDocumentChunks,
  importDocumentFromUrl,
  extractEntitiesFromDocument,
  getApiBase,
} from '../services/api';
import { IngestPipelineStrip } from './IngestPipelineStrip';
import { GlobalSearchBar } from './GlobalSearchBar';

const MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024; // 500 MB

interface DocumentLibraryProps {
  documents: DocumentSummary[];
  selectedDocument: DocumentSummary | null;
  onSelectDocument: (doc: DocumentSummary | null) => void;
  onDocumentsChange: () => void;
  onError?: (message: string) => void;
  availableModels?: AvailableModel[];
  defaultModel?: string;
  /** Investigation workspace: filter list + target for uploads */
  workspaces: WorkspaceSummary[];
  workspaceFilterId: string | null;
  uploadWorkspaceId: string | null;
  onWorkspaceFilterChange: (id: string | null) => void;
  onUploadWorkspaceChange: (id: string | null) => void;
  onCreateWorkspace: (name: string) => Promise<void>;
  onGlobalSearchSelect: (hit: GlobalSearchHit) => void;
}

interface UploadStatus {
  file: File;
  progress: number;
  status: 'uploading' | 'processing' | 'completed' | 'error';
  error?: string;
  stage?: string;
}

export const DocumentLibrary: React.FC<DocumentLibraryProps> = ({
  documents,
  selectedDocument,
  onSelectDocument,
  onDocumentsChange,
  onError,
  availableModels = [],
  defaultModel = 'openai/gpt-4o-mini',
  workspaces,
  workspaceFilterId,
  uploadWorkspaceId,
  onWorkspaceFilterChange,
  onUploadWorkspaceChange,
  onCreateWorkspace,
  onGlobalSearchSelect,
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [uploads, setUploads] = useState<UploadStatus[]>([]);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [chunkPreviewId, setChunkPreviewId] = useState<string | null>(null);
  const [chunkPreview, setChunkPreview] = useState<
    { text: string; start_page: number; end_page: number; chunk_strategy?: string | null }[] | null
  >(null);
  const [newWorkspaceName, setNewWorkspaceName] = useState('');
  const [importMode, setImportMode] = useState<'upload' | 'link'>('upload');
  const [importUrl, setImportUrl] = useState('');
  const [importing, setImporting] = useState(false);
  const [extractModalDoc, setExtractModalDoc] = useState<DocumentSummary | null>(null);
  const [extractLoading, setExtractLoading] = useState(false);
  const [extractResults, setExtractResults] = useState<{ entities: { id: string; name: string; label: string }[]; relationships: { id: string; source: string; target: string; type: string }[] } | null>(null);
  const [extractSource, setExtractSource] = useState<'full_text' | 'chunks'>('full_text');
  const [extractMethod, setExtractMethod] = useState<string>('quality');
  const [extractModel, setExtractModel] = useState<string>('openai/gpt-4o-mini');
  const [extractPushNeo4j, setExtractPushNeo4j] = useState(false);

  // Sync extract model when availableModels loads (in case selection was stale)
  useEffect(() => {
    if (availableModels.length === 0) return;
    const valid = availableModels.some(m => m.id === extractModel);
    if (!valid) setExtractModel(availableModels.some(m => m.id === defaultModel) ? defaultModel : availableModels[0].id);
  }, [availableModels, defaultModel]);

  const mountedRef = useRef(true);
  const clearTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
      if (clearTimerRef.current) clearTimeout(clearTimerRef.current);
      pollAbortRef.current?.abort();
    };
  }, []);

  // Refetch when tab becomes visible (agent/external writes may have occurred)
  useEffect(() => {
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') onDocumentsChange();
    };
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => document.removeEventListener('visibilitychange', onVisibilityChange);
  }, [onDocumentsChange]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const files = Array.from(e.dataTransfer.files).filter(
      f => f.type === 'application/pdf'
    );

    await handleFiles(files);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFileInput = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []).filter(
      f => f.type === 'application/pdf'
    );

    await handleFiles(files);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFiles = async (files: File[]) => {
    for (const file of files) {
      if (file.size > MAX_FILE_SIZE_BYTES) {
        onError?.(`"${file.name}" exceeds 500 MB limit.`);
        continue;
      }

      setUploads(prev => [...prev, {
        file,
        progress: 0,
        status: 'uploading',
      }]);

      try {
        const uploaded = await uploadDocument(
          file,
          (progress) => {
            if (!mountedRef.current) return;
            setUploads((prev) =>
              prev.map((u) => (u.file === file ? { ...u, progress } : u))
            );
          },
          uploadWorkspaceId
        );

        if (!mountedRef.current) return;

        setUploads(prev =>
          prev.map(u =>
            u.file === file ? { ...u, status: 'processing' } : u
          )
        );

        await pollForCompletion(uploaded.id, file.name);
        if (!mountedRef.current) return;

        setUploads(prev =>
          prev.map(u =>
            u.file === file ? { ...u, status: 'completed' } : u
          )
        );

        onDocumentsChange();

      } catch (error) {
        if (!mountedRef.current) return;
        setUploads(prev =>
          prev.map(u =>
            u.file === file
              ? { ...u, status: 'error', error: error instanceof Error ? error.message : 'Upload failed' }
              : u
          )
        );
      }
    }

    if (clearTimerRef.current) clearTimeout(clearTimerRef.current);
    clearTimerRef.current = setTimeout(() => {
      if (mountedRef.current) {
        setUploads(prev => prev.filter(u => u.status !== 'completed'));
      }
    }, 3000);
  };

  const pollFallback = useCallback(async (documentId: string, filename: string) => {
    for (let i = 0; i < 600; i++) {
      await new Promise(r => setTimeout(r, 2000));
      const docs = await listDocuments();
      const doc = docs.find(d => d.id === documentId);
      if (doc?.status === 'indexed') return;
      if (doc?.status === 'error') throw new Error(`Processing failed for "${filename}"`);
    }
    throw new Error(`Processing timeout for "${filename}"`);
  }, []);

  const pollForCompletion = useCallback(async (documentId: string, filename: string) => {
    pollAbortRef.current?.abort();
    const controller = new AbortController();
    pollAbortRef.current = controller;

    // Match main API client: same-origin /api when VITE unset or wrongly set to SPA origin.
    const base =
      typeof window !== 'undefined'
        ? getApiBase()
        : (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8010').replace(/\/$/, '');
    const root = base.startsWith('http') ? base : (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:3000') + base;
    const url = `${root}/documents/${documentId}/progress`;

    return new Promise<void>((resolve, reject) => {
      const es = new EventSource(url);
      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (!mountedRef.current) return;
          setUploads(prev =>
            prev.map(u =>
              u.file.name === filename
                ? { ...u, progress: data.progress ?? u.progress, stage: data.stage }
                : u
            )
          );
          if (data.stage === 'indexed') {
            es.close();
            resolve();
          }
          if (data.stage === 'error') {
            es.close();
            reject(new Error(data.message || `Processing failed for "${filename}"`));
          }
        } catch (_) {}
      };
      es.onerror = () => {
        es.close();
        if (controller.signal.aborted) return;
        pollFallback(documentId, filename).then(resolve).catch(reject);
      };
      controller.signal.addEventListener('abort', () => es.close());
    });
  }, [pollFallback]);

  const handleDelete = async (e: React.MouseEvent, doc: DocumentSummary) => {
    e.stopPropagation();
    if (!confirm(`Delete "${doc.original_name}"?`)) return;

    setDeletingId(doc.id);
    try {
      await deleteDocument(doc.id);
      if (selectedDocument?.id === doc.id) {
        onSelectDocument(null);
      }
      onDocumentsChange();
    } catch (error) {
      onError?.('Failed to delete document');
    } finally {
      setDeletingId(null);
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    });
  };

  const handleImportFromUrl = async () => {
    const url = importUrl.trim();
    if (!url || (!url.includes('drive.google.com') && !url.includes('dropbox.com'))) {
      onError?.('Enter a Google Drive or Dropbox share link');
      return;
    }
    setImporting(true);
    try {
      const uploaded = await importDocumentFromUrl(url);
      setUploads(prev => [...prev, { file: { name: uploaded.filename } as File, progress: 0, status: 'processing' }]);
      await pollForCompletion(uploaded.id, uploaded.filename);
      if (!mountedRef.current) return;
      setUploads(prev => prev.map(u => u.file.name === uploaded.filename ? { ...u, status: 'completed' } : u));
      onDocumentsChange();
      setImportUrl('');
    } catch (e) {
      onError?.(e instanceof Error ? e.message : 'Import failed');
    } finally {
      setImporting(false);
    }
  };

  const handleRunExtract = async () => {
    if (!extractModalDoc) return;
    setExtractLoading(true);
    setExtractResults(null);
    try {
      const res = await extractEntitiesFromDocument(extractModalDoc.id, {
        source: extractSource,
        model: extractModel,
        extraction_method: extractMethod,
        push_to_neo4j: extractPushNeo4j,
      });
      setExtractResults(res);
    } catch (e) {
      onError?.(e instanceof Error ? e.message : 'Extraction failed');
    } finally {
      setExtractLoading(false);
    }
  };

  const handleChunkPreview = async (e: React.MouseEvent, docId: string) => {
    e.stopPropagation();
    if (chunkPreviewId === docId) {
      setChunkPreviewId(null);
      setChunkPreview(null);
      return;
    }
    setChunkPreviewId(docId);
    try {
      const chunks = await getDocumentChunks(docId, 3);
      setChunkPreview(chunks);
    } catch {
      setChunkPreview(null);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Case / workspace — dataset-first navigation */}
      <div className="mb-2 space-y-2">
        <div className="flex items-center gap-2">
          <FolderOpen className="w-4 h-4 text-ink-muted flex-shrink-0" />
          <select
            value={workspaceFilterId ?? ''}
            onChange={(e) =>
              onWorkspaceFilterChange(e.target.value === '' ? null : e.target.value)
            }
            className="flex-1 min-w-0 text-xs bg-surface-muted border border-slate-200 rounded-lg px-2 py-1.5 text-ink"
            title="Filter documents by investigation workspace"
          >
            <option value="">All workspaces</option>
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-ink-muted whitespace-nowrap">Upload to</span>
          <select
            value={uploadWorkspaceId ?? ''}
            onChange={(e) => onUploadWorkspaceChange(e.target.value || null)}
            className="flex-1 min-w-0 text-xs bg-surface-muted border border-slate-200 rounded-lg px-2 py-1.5 text-ink"
          >
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex gap-1">
          <input
            type="text"
            value={newWorkspaceName}
            onChange={(e) => setNewWorkspaceName(e.target.value)}
            placeholder="New workspace name"
            className="flex-1 text-xs px-2 py-1.5 rounded-lg border border-slate-200 bg-surface-muted text-ink"
          />
          <button
            type="button"
            title="Create workspace"
            onClick={async () => {
              const n = newWorkspaceName.trim();
              if (!n) return;
              try {
                await onCreateWorkspace(n);
                setNewWorkspaceName('');
              } catch {
                onError?.('Could not create workspace');
              }
            }}
            className="p-1.5 rounded-lg bg-accent text-white hover:bg-accent-hover"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>
        <GlobalSearchBar workspaceFilterId={workspaceFilterId} onSelectHit={onGlobalSearchSelect} />
      </div>

      {/* Upload / Import Toggle */}
      <div className="flex gap-2 mb-3">
        <button
          type="button"
          onClick={() => setImportMode('upload')}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium ${importMode === 'upload' ? 'bg-accent text-white' : 'text-ink-muted hover:bg-slate-100'}`}
        >
          Upload
        </button>
        <button
          type="button"
          onClick={() => setImportMode('link')}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium ${importMode === 'link' ? 'bg-accent text-white' : 'text-ink-muted hover:bg-slate-100'}`}
        >
          Import from Link
        </button>
      </div>

      {importMode === 'upload' ? (
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`
            relative p-6 border-2 border-dashed rounded-xl transition-all cursor-pointer
            ${isDragging ? 'border-accent bg-accent-light' : 'border-slate-200 hover:border-accent/50 bg-surface-muted'}
          `}
        >
          <input type="file" accept=".pdf" multiple onChange={handleFileInput} className="hidden" id="file-upload" />
          <label htmlFor="file-upload" className="cursor-pointer">
            <div className="flex flex-col items-center text-center">
              <Upload className={`w-8 h-8 mb-2 ${isDragging ? 'text-accent' : 'text-ink-muted'}`} />
              <p className={`text-sm font-medium ${isDragging ? 'text-accent' : 'text-ink'}`}>Drop PDFs here or click to upload</p>
              <p className="text-xs text-ink-muted mt-1">Maximum file size: 500MB</p>
            </div>
          </label>
        </div>
      ) : (
        <div className="p-4 border border-slate-200 rounded-xl bg-surface-muted">
          <p className="text-xs text-ink-muted mb-2">Google Drive or Dropbox share link</p>
          <input
            type="url"
            value={importUrl}
            onChange={(e) => setImportUrl(e.target.value)}
            placeholder="https://drive.google.com/... or https://dropbox.com/..."
            className="w-full px-3 py-2 rounded-lg bg-surface-muted border border-slate-200 text-ink text-sm placeholder-ink-subtle focus:outline-none focus:ring-2 focus:ring-accent/50"
          />
          <button
            onClick={handleImportFromUrl}
            disabled={importing || !importUrl.trim()}
            className="mt-3 flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent-hover disabled:opacity-50 rounded-lg text-sm font-medium text-white"
          >
            {importing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Link2 className="w-4 h-4" />}
            {importing ? 'Importing...' : 'Import'}
          </button>
        </div>
      )}

      {/* Upload Progress */}
      {uploads.length > 0 && (
        <div className="mt-4 space-y-2">
          {uploads.map((upload, idx) => (
            <div key={idx} className="p-3 bg-surface-card border border-slate-200 rounded-lg">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm truncate max-w-[200px] text-ink">
                  {upload.file.name}
                </span>
                {upload.status === 'uploading' && (
                  <Loader2 className="w-4 h-4 animate-spin text-accent" />
                )}
                {upload.status === 'processing' && (
                  <Loader2 className="w-4 h-4 animate-spin text-yellow-400" />
                )}
                {upload.status === 'completed' && (
                  <CheckCircle2 className="w-4 h-4 text-accent" />
                )}
                {upload.status === 'error' && (
                  <AlertCircle className="w-4 h-4 text-red-400" />
                )}
              </div>
              {(upload.status === 'uploading' || upload.status === 'processing') && (
                <div className="w-full bg-slate-200 rounded-full h-1.5">
                  <div
                    className={`h-1.5 rounded-full transition-all ${upload.status === 'uploading' ? 'bg-accent' : 'bg-amber-500'}`}
                    style={{ width: `${upload.progress}%` }}
                  />
                </div>
              )}
              {upload.status === 'processing' && (
                <p className="text-xs text-yellow-400 mt-1">
                  {upload.stage === 'parsing' && 'Parsing...'}
                  {upload.stage === 'chunking' && 'Chunking...'}
                  {upload.stage === 'embedding' && 'Embedding...'}
                  {upload.stage === 'storing' && 'Storing...'}
                  {(!upload.stage || !['parsing','chunking','embedding','storing'].includes(upload.stage)) && 'Processing...'}
                </p>
              )}
              {upload.error && (
                <p className="text-xs text-red-400">{upload.error}</p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Document List */}
      <div className="flex-1 overflow-y-auto mt-4 custom-scrollbar">
        <div className="flex items-center justify-between mb-3 px-2">
          <h3 className="text-[10px] font-bold text-ink-muted uppercase tracking-widest">Documents</h3>
          <div className="flex items-center gap-1">
            <span className="text-xs text-ink-muted">{documents.length} total</span>
            <button
              onClick={onDocumentsChange}
              className="p-1.5 text-ink-muted hover:text-accent rounded transition-colors"
              title="Refresh list"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <div className="space-y-2">
          {/* All Documents Option */}
          <button
            onClick={() => onSelectDocument(null)}
            className={`
              w-full flex items-center gap-3 p-3 rounded-xl transition-all text-left
              ${selectedDocument === null
                ? 'bg-accent-light border border-accent/30'
                : 'bg-surface-muted border border-slate-200 hover:bg-slate-100'
              }
            `}
          >
            <BookOpen className={`w-5 h-5 ${selectedDocument === null ? 'text-accent' : 'text-ink-muted'}`} />
            <div className="flex-1 min-w-0">
              <p className={`text-sm font-medium ${selectedDocument === null ? 'text-accent' : 'text-ink'}`}>All Documents</p>
              <p className="text-xs text-ink-muted">Search across all</p>
            </div>
          </button>

          {/* Individual Documents */}
          {documents.map(doc => (
            <button
              key={doc.id}
              onClick={() => onSelectDocument(doc)}
              className={`
                w-full flex items-center gap-3 p-3 rounded-xl transition-all text-left group
                ${selectedDocument?.id === doc.id
                  ? 'bg-indigo-500/10 border border-indigo-500/30'
                  : 'bg-white/[0.02] border border-white/5 hover:bg-white/5'
                }
              `}
            >
              <FileText className={`
                w-5 h-5 flex-shrink-0
                ${doc.status === 'indexed' ? 'text-accent' : 'text-ink-muted'}
              `} />

              <div className="flex-1 min-w-0">
                <p className={`text-sm font-medium truncate ${selectedDocument?.id === doc.id ? 'text-accent' : 'text-ink'}`}>
                  {doc.original_name}
                </p>
                <p className="text-xs text-ink-muted">
                  {doc.total_pages} pages &bull; {doc.chunk_count} chunks &bull; {formatDate(doc.upload_date)}
                </p>
                {(doc.status === 'processing' || doc.status === 'indexed' || doc.status === 'error') && (
                  <IngestPipelineStrip
                    status={doc.status}
                    ingestStage={doc.ingest_stage}
                    errorMessage={doc.error_message}
                  />
                )}
              </div>

              <div className="flex items-center gap-2">
                {doc.status === 'processing' && (
                  <Loader2 className="w-4 h-4 animate-spin text-yellow-400" />
                )}
                {doc.status === 'error' && (
                  <AlertCircle className="w-4 h-4 text-red-400" />
                )}
                {doc.status === 'indexed' && (
                  <>
                    <button
                      onClick={(e) => { e.stopPropagation(); setExtractModalDoc(doc); setExtractResults(null); }}
                      className="p-1.5 text-ink-muted hover:text-accent hover:bg-accent-light rounded transition-colors text-xs"
                      title="Extract entities"
                    >
                      <Network className="w-4 h-4" />
                    </button>
                    <button
                      onClick={(e) => handleChunkPreview(e, doc.id)}
                      className="p-1.5 text-ink-muted hover:text-accent hover:bg-accent-light rounded transition-colors text-xs"
                      title="Preview chunks"
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                  </>
                )}

                <button
                  onClick={(e) => handleDelete(e, doc)}
                  disabled={deletingId === doc.id}
                  className="p-1.5 text-ink-muted hover:text-red-600 hover:bg-red-50 rounded transition-colors opacity-0 group-hover:opacity-100"
                >
                  {deletingId === doc.id ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Trash2 className="w-4 h-4" />
                  )}
                </button>
              </div>
            </button>
          ))}
        </div>

        {chunkPreview && chunkPreviewId && (
          <div className="mt-4 p-3 bg-surface-muted border border-slate-200 rounded-lg">
            <p className="text-[10px] font-bold text-ink-muted uppercase tracking-widest mb-2">Chunk preview (first 3)</p>
            {chunkPreview.map((c, i) => (
              <div key={i} className="mb-2 last:mb-0">
                <p className="text-[10px] text-ink-muted">
                  Chunk {i + 1} (p{c.start_page}-{c.end_page})
                  {c.chunk_strategy ? ` · ${c.chunk_strategy}` : ''}
                </p>
                <p className="text-xs text-ink mt-0.5 line-clamp-2">{c.text}</p>
              </div>
            ))}
          </div>
        )}

        {extractModalDoc && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setExtractModalDoc(null)}>
            <div className="bg-surface-card border border-slate-200 rounded-xl p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto shadow-xl" onClick={e => e.stopPropagation()}>
              <div className="flex justify-between items-start mb-4">
                <h3 className="text-lg font-bold text-ink">Extract Entities from {extractModalDoc.original_name}</h3>
                <button onClick={() => setExtractModalDoc(null)} className="text-ink-muted hover:text-ink">×</button>
              </div>
              <div className="space-y-3 mb-4">
                <div>
                  <label className="text-xs text-slate-500">Source</label>
                  <div className="flex gap-2 mt-1">
                    <button onClick={() => setExtractSource('full_text')} className={`px-3 py-1.5 rounded text-xs ${extractSource === 'full_text' ? 'bg-accent text-white' : 'bg-surface-muted'}`}>Full Document</button>
                    <button onClick={() => setExtractSource('chunks')} className={`px-3 py-1.5 rounded text-xs ${extractSource === 'chunks' ? 'bg-accent text-white' : 'bg-surface-muted'}`}>Existing Chunks</button>
                  </div>
                </div>
                <div>
                  <label className="text-xs text-slate-500">Model</label>
                  <select value={extractModel} onChange={e => setExtractModel(e.target.value)} className="mt-1 w-full px-3 py-2 rounded bg-surface-muted text-sm">
                    {(availableModels.length ? availableModels : [
                      { id: 'openai/gpt-4o-mini', name: 'GPT-4o mini' },
                      { id: 'moonshotai/kimi-k2.5', name: 'Kimi' },
                      { id: 'minimax/minimax-m2.5', name: 'Minimax' },
                      { id: 'anthropic/claude-3.5-sonnet', name: 'Sonnet' },
                    ]).map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-slate-500">Extraction</label>
                  <select value={extractMethod} onChange={e => setExtractMethod(e.target.value)} className="mt-1 w-full px-3 py-2 rounded bg-surface-muted text-sm">
                    <option value="quality">Two-Pass (Quality)</option>
                    <option value="fast">Single-Pass (Fast)</option>
                    <option value="ftm">FTM Schema-Guided</option>
                  </select>
                </div>
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={extractPushNeo4j} onChange={e => setExtractPushNeo4j(e.target.checked)} />
                  <span className="text-sm">Push to Neo4j</span>
                </label>
              </div>
              <button onClick={handleRunExtract} disabled={extractLoading} className="px-4 py-2 bg-accent hover:bg-accent-hover rounded-lg text-sm font-medium disabled:opacity-50 text-white">
                {extractLoading ? 'Extracting...' : 'Run'}
              </button>
              {extractResults && (
                <div className="mt-6">
                  <p className="text-xs text-slate-500 mb-2">{extractResults.entities.length} entities, {extractResults.relationships.length} relationships</p>
                  <div className="flex gap-2 mb-2">
                    <button onClick={() => { const rows = extractResults.entities.map(e=>[(e as {id?: string}).id || e.name.replace(/\s+/g,'_').toLowerCase(),e.name,e.label]); const csv = [['entityId:ID','name',':LABEL'],...rows].map(r=>r.join(',')).join('\n'); const a = document.createElement('a'); a.href = 'data:text/csv,'+encodeURIComponent(csv); a.download='entities.csv'; a.click(); }} className="text-xs px-2 py-1 bg-surface-muted rounded">Download CSV</button>
                    <button onClick={() => { const a = document.createElement('a'); a.href = 'data:application/json,'+encodeURIComponent(JSON.stringify(extractResults, null, 2)); a.download='extract.json'; a.click(); }} className="text-xs px-2 py-1 bg-slate-800 rounded">Download JSON</button>
                  </div>
                  <div className="max-h-48 overflow-y-auto text-xs font-mono bg-slate-800 rounded p-2">
                    {extractResults.entities.slice(0, 10).map((e, i) => <div key={e.id || i}>{e.name} ({e.label})</div>)}
                    {extractResults.entities.length > 10 && <div className="text-slate-500">... and {extractResults.entities.length - 10} more</div>}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {documents.length === 0 && (
          <div className="text-center py-8 text-slate-500">
            <FileText className="w-12 h-12 mx-auto mb-3 text-slate-600" />
            <p className="text-sm">No documents yet</p>
            <p className="text-xs mt-1">Upload a PDF to get started</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default DocumentLibrary;
