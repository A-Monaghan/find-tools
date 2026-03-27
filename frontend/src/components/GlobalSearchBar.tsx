/**
 * Corpus-wide chunk search (locate then ask — not full RAG).
 */

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { Search, Loader2 } from 'lucide-react';
import type { GlobalSearchHit } from '../types';
import { searchCorpus } from '../services/api';

interface GlobalSearchBarProps {
  workspaceFilterId: string | null;
  onSelectHit: (hit: GlobalSearchHit) => void;
}

export const GlobalSearchBar: React.FC<GlobalSearchBarProps> = ({
  workspaceFilterId,
  onSelectHit,
}) => {
  const [q, setQ] = useState('');
  const [hits, setHits] = useState<GlobalSearchHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const run = useCallback(async () => {
    const term = q.trim();
    if (term.length < 2) {
      setHits([]);
      return;
    }
    setLoading(true);
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const res = await searchCorpus(term, workspaceFilterId, controller.signal);
      setHits(res);
    } catch {
      setHits([]);
    } finally {
      setLoading(false);
    }
  }, [q, workspaceFilterId]);

  useEffect(() => {
    const t = setTimeout(() => {
      if (q.trim().length >= 2) run();
      else setHits([]);
    }, 350);
    return () => clearTimeout(t);
  }, [q, run]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  return (
    <div className="relative mb-3">
      <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-surface-muted border border-slate-200">
        <Search className="w-4 h-4 text-ink-muted flex-shrink-0" />
        <input
          type="search"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder="Search corpus…"
          className="flex-1 bg-transparent text-sm text-ink placeholder-ink-subtle outline-none min-w-0"
        />
        {loading && <Loader2 className="w-4 h-4 animate-spin text-accent" />}
      </div>
      {open && hits.length > 0 && (
        <ul className="absolute z-50 left-0 right-0 mt-1 max-h-80 overflow-y-auto rounded-xl border border-slate-200 bg-surface-card shadow-lg text-left">
          {hits.map((h) => (
            <li key={`${h.document_id}-${h.chunk_id}`}>
              <button
                type="button"
                className="w-full text-left px-3 py-2 hover:bg-slate-50 border-b border-slate-100 last:border-0"
                onClick={() => {
                  onSelectHit(h);
                  setOpen(false);
                  setQ('');
                  setHits([]);
                }}
              >
                <p className="text-xs font-medium text-ink truncate">{h.document_name}</p>
                <p className="text-[10px] text-ink-muted">p.{h.start_page}-{h.end_page}</p>
                <p className="text-xs text-ink-muted line-clamp-2 mt-0.5">{h.snippet}</p>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
