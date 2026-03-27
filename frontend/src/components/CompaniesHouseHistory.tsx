/**
 * Companies House > History — list of pipeline runs.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { History, Download, Trash2, RefreshCw, Loader2 } from 'lucide-react';
import { listCHJobs, deleteCHJob, getCHDownloadUrl, type CHJob } from '../services/api';

function formatRelativeTime(ts: number): string {
  const s = Math.floor((Date.now() / 1000) - ts);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export const CompaniesHouseHistory: React.FC = () => {
  const [jobs, setJobs] = useState<CHJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const loadJobs = useCallback(async () => {
    setLoading(true);
    try {
      const { jobs: j } = await listCHJobs();
      setJobs(j);
    } catch {
      setJobs([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  // Refetch when tab becomes visible (agent/external writes may have occurred)
  useEffect(() => {
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') loadJobs();
    };
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => document.removeEventListener('visibilitychange', onVisibilityChange);
  }, [loadJobs]);

  const handleDelete = async (jobId: string) => {
    if (!confirm('Delete this run and its data?')) return;
    setDeletingId(jobId);
    try {
      await deleteCHJob(jobId);
      setJobs((prev) => prev.filter((j) => j.job_id !== jobId));
    } catch (err) {
      console.error('Delete failed:', err);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-6 sm:p-10 custom-scrollbar">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="bg-accent p-2 rounded-xl">
              <History className="w-6 h-6 text-white" />
            </div>
            <h1 className="text-xl font-bold text-ink">Pipeline History</h1>
          </div>
          <button
            onClick={loadJobs}
            disabled={loading}
            className="p-2 text-ink-muted hover:text-ink rounded-lg hover:bg-slate-100"
            title="Refresh"
          >
            <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {loading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-8 h-8 text-accent animate-spin" />
          </div>
        ) : jobs.length === 0 ? (
          <div className="text-center py-12 text-ink-muted">
            No pipeline runs yet. Run a search from the Companies House tab.
          </div>
        ) : (
          <ul className="space-y-2">
            {jobs.map((job) => (
              <li
                key={job.job_id}
                className="flex items-center justify-between gap-4 py-3 px-4 rounded-xl bg-surface-card border border-slate-200"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-ink truncate" title={job.search_value}>
                    {job.search_value}
                  </p>
                  <p className="text-xs text-ink-muted mt-0.5">
                    {formatRelativeTime(job.created_at)}
                    {job.job_kind === 'documents' || job.search_type === 'documents'
                      ? ` · ${job.documents_downloaded ?? 0} PDF(s) downloaded`
                      : ` · ${job.companies_processed ?? 0} companies${job.filings != null ? ` · ${job.filings} filings` : ''}`}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <a
                    href={getCHDownloadUrl(job.job_id)}
                    download={`ch_pipeline_${job.job_id}.zip`}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-200 hover:bg-slate-300 text-ink text-xs font-medium"
                  >
                    <Download className="w-3.5 h-3.5" />
                    Download
                  </a>
                  <button
                    onClick={() => handleDelete(job.job_id)}
                    disabled={deletingId === job.job_id}
                    className="p-1.5 rounded-lg text-ink-muted hover:text-red-600 hover:bg-red-50 disabled:opacity-50"
                    title="Delete"
                  >
                    {deletingId === job.job_id ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Trash2 className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};
