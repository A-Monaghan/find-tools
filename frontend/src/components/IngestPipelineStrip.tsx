import React from 'react';
import { Check, Loader2, AlertCircle } from 'lucide-react';

interface IngestPipelineStripProps {
  status: 'processing' | 'indexed' | 'error';
  ingestStage?: string | null;
  errorMessage?: string | null;
}

const STAGES = [
  { key: 'upload', match: () => true },
  { key: 'parse', match: (s: string | null | undefined) => s === 'parse' || s === 'cleanup' },
  { key: 'embed', match: (s: string | null | undefined) => s === 'embed' },
  { key: 'index', match: (s: string | null | undefined) => s === 'index' },
];

/**
 * Horizontal ingest progress aligned with backend ingest_stage (parse → embed → index).
 */
export const IngestPipelineStrip: React.FC<IngestPipelineStripProps> = ({
  status,
  ingestStage,
  errorMessage,
}) => {
  if (status === 'error') {
    return (
      <div className="flex items-center gap-1 mt-1 text-[10px] text-red-500">
        <AlertCircle className="w-3 h-3 flex-shrink-0" />
        <span className="truncate">{errorMessage || 'Ingest failed'}</span>
      </div>
    );
  }

  if (status === 'indexed') {
    return (
      <div className="flex items-center gap-1 mt-1 text-[10px] text-emerald-600">
        <Check className="w-3 h-3" />
        <span>Indexed</span>
      </div>
    );
  }

  // processing
  let activeIdx = 0;
  if (ingestStage === 'embed') activeIdx = 2;
  else if (ingestStage === 'index') activeIdx = 3;
  else if (ingestStage === 'parse' || ingestStage === 'cleanup') activeIdx = 1;

  return (
    <div className="flex items-center gap-0.5 mt-1.5" title={`Stage: ${ingestStage || 'starting'}`}>
      {STAGES.map((st, i) => {
        const done = i < activeIdx;
        const active = i === activeIdx;
        return (
          <React.Fragment key={st.key}>
            {i > 0 && <span className="text-ink-subtle text-[8px] px-0.5">→</span>}
            <span
              className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9px] font-medium uppercase tracking-tight ${
                done
                  ? 'bg-emerald-500/15 text-emerald-700'
                  : active
                    ? 'bg-amber-500/20 text-amber-800'
                    : 'bg-slate-100 text-ink-muted'
              }`}
            >
              {active && i === activeIdx && <Loader2 className="w-2.5 h-2.5 animate-spin" />}
              {st.key}
            </span>
          </React.Fragment>
        );
      })}
    </div>
  );
};
