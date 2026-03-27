/**
 * OSINT Toolkit — embeds osintframework.com in an iframe.
 * "Open in new tab" link provided in case the site blocks embedding (X-Frame-Options).
 */
import { ExternalLink } from 'lucide-react';

const OSINT_URL = 'https://osintframework.com/';

export function OsintToolkit() {
  return (
    <div className="h-full flex flex-col bg-surface relative">
      <div className="absolute top-4 left-4 z-10 px-2 py-1 rounded-md text-[10px] font-medium bg-amber-500/15 text-amber-800 border border-amber-500/30">
        External directory — no case data sent to RAG
      </div>
      <a
        href={OSINT_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="absolute top-4 right-4 z-10 flex items-center gap-1.5 px-3 py-1.5 text-xs text-ink-muted hover:text-ink hover:bg-slate-100 rounded-lg transition-colors"
      >
        <ExternalLink className="w-3.5 h-3.5" />
        Open in new tab
      </a>
      <iframe
        src={OSINT_URL}
        title="OSINT Framework"
        className="w-full flex-1 min-h-0 border-0"
        sandbox="allow-scripts allow-same-origin allow-popups"
      />
    </div>
  );
}
