/**
 * Citation + retrieval trace panel (sources for grounded answers).
 * `layout="rail"`: embedded in flex row (desktop). `layout="overlay"`: full-screen sheet (mobile).
 */

import React from 'react';
import { X, FileText, ChevronRight, Quote, Activity } from 'lucide-react';
import { Citation, RetrievedChunk, RetrievalTrace } from '../types';

interface CitationPanelProps {
  isOpen: boolean;
  onClose: () => void;
  citations: Citation[];
  chunks: RetrievedChunk[];
  /** HyDE / fusion / CRAG diagnostics */
  retrievalTrace?: RetrievalTrace | null;
  layout?: 'overlay' | 'rail';
  /** Jump to document in sidebar (case-centric workflow) */
  onFocusDocument?: (documentId: string) => void;
}

export const CitationPanel: React.FC<CitationPanelProps> = ({
  isOpen,
  onClose,
  citations,
  chunks,
  retrievalTrace,
  layout = 'overlay',
  onFocusDocument,
}) => {
  if (!isOpen) return null;

  const isRail = layout === 'rail';

  const formatPageRange = (start: number, end: number) => {
    if (start === end) return `Page ${start}`;
    return `Pages ${start}-${end}`;
  };

  const citationData = citations.map((citation) => {
    const chunk = chunks.find((c) => c.chunk_id === citation.chunk_id);
    return {
      ...citation,
      fullText: chunk?.text || citation.evidence_quote,
    };
  });

  const panelBody = (
    <>
      <div className="flex items-center justify-between p-4 border-b border-slate-200 flex-shrink-0">
        <div className="flex items-center gap-2">
          <Quote className="w-5 h-5 text-accent" />
          <h2 className="text-lg font-semibold text-ink">Sources</h2>
          <span className="text-sm text-ink-muted">({citations.length})</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-2 text-ink-muted hover:text-ink hover:bg-slate-100 rounded-lg transition-colors"
          title="Close (backtick toggles)"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar min-h-0">
        {/* Retrieval trace — investigator transparency */}
        {retrievalTrace && (
          <div className="mb-4 p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs">
            <div className="flex items-center gap-2 font-semibold text-ink mb-2">
              <Activity className="w-4 h-4 text-accent" />
              Retrieval trace
            </div>
            <ul className="space-y-1 text-ink-muted">
              <li>HyDE: {retrievalTrace.hyde_used ? 'yes' : 'no'}</li>
              <li>
                Search: {retrievalTrace.fusion_enabled ? `fusion (α=${retrievalTrace.fusion_alpha ?? '—'})` : 'dense only'}
              </li>
              {retrievalTrace.rrf_k != null && <li>RRF k: {retrievalTrace.rrf_k}</li>}
              {retrievalTrace.crag_action && <li>CRAG: {retrievalTrace.crag_action}</li>}
              <li>Web augmented: {retrievalTrace.web_augmented ? 'yes' : 'no'}</li>
            </ul>
            {retrievalTrace.chunks.length > 0 && (
              <details className="mt-2">
                <summary className="cursor-pointer text-accent text-[11px]">Chunk ranks (dense / BM25)</summary>
                <div className="mt-1 max-h-32 overflow-y-auto font-mono text-[10px] space-y-0.5">
                  {retrievalTrace.chunks.slice(0, 12).map((c) => (
                    <div key={c.chunk_id}>
                      {c.chunk_id.slice(0, 8)}… d:{c.dense_rank} b:{c.bm25_rank}
                      {c.fused_score != null && ` σ:${c.fused_score}`}
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        )}

        {citationData.length === 0 ? (
          <div className="text-center py-8 text-ink-muted">
            <Quote className="w-12 h-12 mx-auto mb-3 text-ink-subtle" />
            <p className="text-sm">No citations available</p>
          </div>
        ) : (
          <div className="space-y-4">
            {citationData.map((citation, index) => (
              <div
                key={citation.chunk_id}
                className="border border-slate-200 rounded-xl overflow-hidden bg-surface-muted"
              >
                <div className="bg-surface-card px-4 py-3 border-b border-slate-200">
                  <div className="flex items-center gap-2">
                    <span className="flex items-center justify-center w-6 h-6 bg-accent/20 text-accent text-sm font-medium rounded-full">
                      {index + 1}
                    </span>
                    <FileText className="w-4 h-4 text-ink-muted" />
                    <span className="text-sm font-medium text-ink truncate">{citation.document_name}</span>
                  </div>
                  <div className="flex items-center gap-2 mt-1 ml-8 text-xs text-ink-muted flex-wrap">
                    <span>{formatPageRange(citation.start_page, citation.end_page)}</span>
                    <span>•</span>
                    <span className="text-accent">{Math.round(citation.relevance_score * 100)}% match</span>
                    {onFocusDocument && (
                      <>
                        <span>•</span>
                        <button
                          type="button"
                          className="text-accent hover:underline"
                          onClick={() => onFocusDocument(citation.document_id)}
                        >
                          Focus in library
                        </button>
                      </>
                    )}
                  </div>
                </div>

                <div className="p-4">
                  <blockquote className="text-sm text-ink border-l-4 border-accent/50 pl-3 italic">
                    &ldquo;{citation.evidence_quote}&rdquo;
                  </blockquote>

                  {citation.fullText !== citation.evidence_quote && (
                    <div className="mt-3">
                      <details className="text-xs">
                        <summary className="cursor-pointer text-accent hover:text-accent-hover flex items-center gap-1">
                          <ChevronRight className="w-3 h-3" />
                          Show full context
                        </summary>
                        <p className="mt-2 text-ink-muted leading-relaxed">{citation.fullText}</p>
                      </details>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );

  if (isRail) {
    return (
      <div className="h-full w-full max-w-[420px] bg-surface-card flex flex-col border-l border-slate-200 shadow-inner">
        {panelBody}
      </div>
    );
  }

  return (
    <>
      <div
        className="fixed inset-0 bg-slate-900/20 backdrop-blur-sm z-40"
        onClick={onClose}
        aria-hidden
      />
      <div className="fixed right-0 top-0 h-full w-96 max-w-[100vw] bg-surface-card border-l border-slate-200 shadow-xl z-50 flex flex-col">
        {panelBody}
      </div>
    </>
  );
};

export default CitationPanel;
