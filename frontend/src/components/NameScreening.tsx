/**
 * Fuzzy name + optional DOB screening against OpenSanctions (hosted match / FTM model),
 * OCCRP Aleph, and Sayari Graph. Keys: browser (below) or server .env — per-request overrides.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Search, AlertCircle, Download } from 'lucide-react';
import { useUnifiedConfig } from '../context/UnifiedConfigContext';
import { ScreeningApiKeySection } from './ScreeningApiKeySection';
import {
  getScreeningStatus,
  runNameScreening,
  type ScreeningStatusResponse,
  type ScreeningNameSearchResponse,
  type ScreeningSource,
} from '../services/api';
import {
  buildScreeningExportRows,
  downloadScreeningCsv,
  SCREENING_SCORE_EXPORT_MIN,
} from '../utils/screeningCsv';
import Spinner from './Spinner';

type SourceKey = ScreeningSource;

function datasetReady(
  id: SourceKey,
  status: ScreeningStatusResponse | null,
  screening: {
    openSanctionsApiKey: string;
    alephApiKey: string;
    sayariClientId: string;
    sayariClientSecret: string;
  }
): boolean {
  if (id === 'opensanctions') {
    return !!(screening.openSanctionsApiKey?.trim() || status?.opensanctions);
  }
  if (id === 'aleph') {
    return !!(screening.alephApiKey?.trim() || status?.aleph);
  }
  return !!(
    (screening.sayariClientId?.trim() && screening.sayariClientSecret?.trim()) ||
    status?.sayari
  );
}

const SOURCE_META: { id: SourceKey; label: string; hint: string }[] = [
  {
    id: 'opensanctions',
    label: 'OpenSanctions',
    hint: 'Hosted match API — default collection (FTM entity model; datasets in each hit).',
  },
  {
    id: 'aleph',
    label: 'Aleph (OCCRP)',
    hint: 'Investigative entity search — public API base shown when configured.',
  },
  {
    id: 'sayari',
    label: 'Sayari',
    hint: 'Graph entity search (OAuth on server).',
  },
];

export const NameScreening: React.FC = () => {
  const { config } = useUnifiedConfig();
  const screening = config.screening;

  const [name, setName] = useState('');
  const [dob, setDob] = useState('');
  const [status, setStatus] = useState<ScreeningStatusResponse | null>(null);
  const [statusErr, setStatusErr] = useState<string | null>(null);
  const [selected, setSelected] = useState<Record<SourceKey, boolean>>({
    opensanctions: true,
    aleph: true,
    sayari: true,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ScreeningNameSearchResponse | null>(null);

  useEffect(() => {
    getScreeningStatus()
      .then((s) => {
        setStatus(s);
        setStatusErr(null);
      })
      .catch((e: unknown) => {
        setStatusErr(e instanceof Error ? e.message : 'Failed to load screening status');
      });
  }, []);

  const toggle = useCallback((id: SourceKey) => {
    setSelected((prev) => ({ ...prev, [id]: !prev[id] }));
  }, []);

  const ready = useMemo(
    () => ({
      opensanctions: datasetReady('opensanctions', status, screening),
      aleph: datasetReady('aleph', status, screening),
      sayari: datasetReady('sayari', status, screening),
    }),
    [status, screening]
  );

  const activeSources = SOURCE_META.filter((m) => selected[m.id] && ready[m.id]).map((m) => m.id);
  const canSearch =
    name.trim().length >= 2 && activeSources.length > 0 && !loading;

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSearch) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await runNameScreening({
        name: name.trim(),
        dob: dob.trim() || null,
        sources: activeSources,
        opensanctions_api_key: screening.openSanctionsApiKey.trim() || undefined,
        aleph_api_key: screening.alephApiKey.trim() || undefined,
        aleph_api_base: screening.alephApiBase.trim() || undefined,
        sayari_client_id: screening.sayariClientId.trim() || undefined,
        sayari_client_secret: screening.sayariClientSecret.trim() || undefined,
        sayari_api_base: screening.sayariApiBase.trim() || undefined,
      });
      setResult(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-6 sm:p-10 custom-scrollbar bg-surface">
      <div className="max-w-4xl mx-auto space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-ink">Name screening</h1>
          <p className="text-sm text-ink-muted mt-1">
            Fuzzy-ranked results from upstream APIs. Date of birth narrows OpenSanctions and Sayari
            field search when provided.
          </p>
        </div>

        {statusErr && (
          <div className="flex items-start gap-2 p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-900 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{statusErr}</span>
          </div>
        )}

        <ScreeningApiKeySection compact />

        {/* API / dataset zone — checkbox per upstream */}
        <section
          className="rounded-2xl border border-slate-200 bg-surface-card p-5 shadow-sm"
          aria-label="Screening APIs"
        >
          <h2 className="text-sm font-semibold text-ink mb-3">APIs / datasets</h2>
          <p className="text-xs text-ink-muted mb-4">
            Enable each source that has a key above <strong>or</strong> on the server (
            <span className="font-mono">OPENSANCTIONS_API_KEY</span>, <span className="font-mono">ALEPH_API_KEY</span>,{' '}
            <span className="font-mono">SAYARI_CLIENT_ID</span> / <span className="font-mono">SAYARI_CLIENT_SECRET</span>
            ). You can also manage these under <strong>About → API keys</strong>.
          </p>
          <ul className="space-y-3">
            {SOURCE_META.map((m) => {
              const isReady = ready[m.id];
              return (
                <li
                  key={m.id}
                  className="flex items-start gap-3 p-3 rounded-xl bg-slate-50/80 border border-slate-100"
                >
                  <input
                    type="checkbox"
                    id={`src-${m.id}`}
                    className="mt-1 rounded border-slate-300"
                    checked={isReady && selected[m.id]}
                    disabled={!isReady}
                    onChange={() => isReady && toggle(m.id)}
                  />
                  <label
                    htmlFor={`src-${m.id}`}
                    className={`flex-1 min-w-0 ${isReady ? 'cursor-pointer' : 'cursor-not-allowed'}`}
                  >
                    <span className="font-medium text-ink">{m.label}</span>
                    <p className="text-xs text-ink-muted mt-0.5">{m.hint}</p>
                    {!isReady && (
                      <p className="text-xs text-amber-800 mt-1">
                        No key — add credentials above or set server environment variables.
                      </p>
                    )}
                  </label>
                </li>
              );
            })}
          </ul>
          {status && (
            <p className="text-[11px] text-ink-muted mt-4 font-mono break-all">
              Aleph base: {status.aleph_api_base} · Sayari base: {status.sayari_api_base}
            </p>
          )}
        </section>

        <form onSubmit={onSubmit} className="rounded-2xl border border-slate-200 bg-surface-card p-5 shadow-sm space-y-4">
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-ink-muted mb-1">Full name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Jane Smith"
                className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-white text-ink text-sm"
                autoComplete="off"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-ink-muted mb-1">
                Date of birth <span className="font-normal">(optional)</span>
              </label>
              <input
                type="text"
                value={dob}
                onChange={(e) => setDob(e.target.value)}
                placeholder="YYYY, YYYY-MM, or YYYY-MM-DD"
                className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-white text-ink text-sm font-mono"
                autoComplete="off"
              />
            </div>
          </div>
          <button
            type="submit"
            disabled={!canSearch}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold bg-accent text-white shadow-sm disabled:opacity-50 disabled:cursor-not-allowed hover:opacity-95"
          >
            {loading ? <Spinner /> : <Search className="w-4 h-4" />}
            Search
          </button>
        </form>

        {error && (
          <div className="p-3 rounded-xl bg-red-500/10 border border-red-200 text-red-900 text-sm">{error}</div>
        )}

        {result && (
          <ScreeningResults
            data={result}
            queryName={name.trim()}
            queryDob={dob.trim() || null}
          />
        )}
      </div>
    </div>
  );
};

function ScreeningResults({
  data,
  queryName,
  queryDob,
}: {
  data: ScreeningNameSearchResponse;
  queryName: string;
  queryDob: string | null;
}) {
  const exportRows = buildScreeningExportRows(data, queryName, queryDob);

  const onDownloadCsv = () => {
    const base = queryName || 'screening';
    downloadScreeningCsv(exportRows, base);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <h2 className="text-lg font-semibold text-ink">Results</h2>
        {exportRows.length > 0 && (
          <button
            type="button"
            onClick={onDownloadCsv}
            className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold border border-slate-200 bg-white text-ink hover:bg-slate-50"
          >
            <Download className="w-4 h-4" />
            Download CSV (score ≥ {SCREENING_SCORE_EXPORT_MIN}, {exportRows.length} row
            {exportRows.length === 1 ? '' : 's'})
          </button>
        )}
      </div>

      <section className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4 text-sm text-ink space-y-2">
        <h3 className="font-semibold text-ink">Certainty, true positives, and false positives</h3>
        <p className="text-ink-muted leading-relaxed">
          The <strong>fuzzy score</strong> is string similarity between your query name and each hit&apos;s label — it
          is <strong>not</strong> a probability that the record is the same person. A &quot;true positive&quot; (the
          intended individual) vs &quot;false positive&quot; (wrong person, weak relevance, or homonym){' '}
          <strong>cannot</strong> be decided from scores alone; investigators should corroborate with DOB, official
          identifiers, jurisdiction, and source documents.
        </p>
        <p className="text-ink-muted leading-relaxed">
          The CSV includes rows with fuzzy score <strong>≥ {SCREENING_SCORE_EXPORT_MIN}</strong>, plus columns{' '}
          <span className="font-mono text-xs">false_positive_risk</span>,{' '}
          <span className="font-mono text-xs">certainty_summary</span>, and{' '}
          <span className="font-mono text-xs">investigator_notes</span> — heuristic guidance only, not legal advice.
        </p>
        {exportRows.length === 0 && (
          <p className="text-amber-800 text-xs">
            No rows meet the export threshold — lower scores are hidden from the CSV (still visible in tables above).
          </p>
        )}
      </section>

      <Block title="OpenSanctions" section={data.opensanctions} />
      <Block title="Aleph" section={data.aleph} />
      <Block title="Sayari" section={data.sayari} />
    </div>
  );
}

function Block({
  title,
  section,
}: {
  title: string;
  section: Record<string, unknown> | null;
}) {
  if (!section) {
    return (
      <section className="rounded-2xl border border-slate-100 p-4 bg-slate-50/50">
        <h3 className="text-sm font-semibold text-ink-muted mb-1">{title}</h3>
        <p className="text-xs text-ink-muted">Not queried.</p>
      </section>
    );
  }
  const skipped = section.skipped === true;
  const ok = section.ok === true;
  const err = typeof section.error === 'string' ? section.error : null;
  const matches = Array.isArray(section.matches) ? section.matches : [];

  return (
    <section className="rounded-2xl border border-slate-200 bg-surface-card p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-ink mb-2">{title}</h3>
      {skipped && <p className="text-xs text-amber-800 mb-2">{err || 'Skipped.'}</p>}
      {!skipped && !ok && err && <p className="text-xs text-red-800 mb-2">{err}</p>}
      {ok && matches.length === 0 && <p className="text-xs text-ink-muted">No matches.</p>}
      {ok && matches.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead>
              <tr className="text-ink-muted border-b border-slate-200">
                <th className="py-2 pr-2">Score</th>
                <th className="py-2 pr-2">Label / caption</th>
                <th className="py-2 pr-2">Meta</th>
              </tr>
            </thead>
            <tbody>
              {matches.map((row, i) => {
                const r = row as Record<string, unknown>;
                const score = r.score;
                const label =
                  (r.caption as string) ||
                  (r.label as string) ||
                  (r.name as string) ||
                  '—';
                const id = r.id != null ? String(r.id) : '';
                const datasets = r.datasets;
                const metaParts: string[] = [];
                if (id) metaParts.push(`id: ${id}`);
                if (Array.isArray(datasets)) metaParts.push(`datasets: ${datasets.join(', ')}`);
                if (r.schema) metaParts.push(`schema: ${String(r.schema)}`);
                if (r.collection) metaParts.push(`collection: ${String(r.collection)}`);
                if (r.entity_url) metaParts.push(String(r.entity_url));
                return (
                  <tr key={i} className="border-b border-slate-100 last:border-0">
                    <td className="py-2 pr-2 font-mono text-ink">{String(score ?? '—')}</td>
                    <td className="py-2 pr-2 text-ink">{label}</td>
                    <td className="py-2 text-ink-muted break-all">{metaParts.join(' · ')}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
