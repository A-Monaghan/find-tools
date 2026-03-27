/**
 * Companies House > Settings — API key is configured on About (single place).
 */
import React from 'react';
import { Settings, Building2 } from 'lucide-react';

export const CompaniesHouseSettings: React.FC = () => {
  return (
    <div className="h-full overflow-y-auto p-6 sm:p-10 custom-scrollbar">
      <div className="max-w-2xl mx-auto space-y-8">
        <div className="flex items-center gap-3 mb-6">
          <div className="bg-accent p-2 rounded-xl">
            <Settings className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-xl font-bold text-ink">Companies House Settings</h1>
        </div>

        <div className="bg-surface-card border border-slate-200 rounded-xl p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <Building2 className="w-5 h-5 text-accent shrink-0 mt-0.5" />
            <div>
              <h2 className="text-lg font-semibold text-ink mb-2">API key</h2>
              <p className="text-sm text-ink-muted leading-relaxed">
                The Companies House API key is configured under About → <strong className="text-ink">API keys</strong> so all credentials stay in one place.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
