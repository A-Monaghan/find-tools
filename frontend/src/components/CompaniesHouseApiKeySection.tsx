/**
 * Companies House API key — lives in About with other keys (single place in the app).
 */
import React from 'react';
import { Building2 } from 'lucide-react';
import { useUnifiedConfig } from '../context/UnifiedConfigContext';

export const CompaniesHouseApiKeySection: React.FC = () => {
  const { config, setCompaniesHouseConfig } = useUnifiedConfig();

  return (
    <section id="api-keys-ch" className="scroll-mt-4">
      <h2 className="text-lg font-semibold text-ink mb-3 flex items-center gap-2">
        <Building2 className="w-5 h-5 text-accent" />
        Companies House API key
      </h2>
      <p className="text-sm text-ink-muted mb-3">
        Optional. Improves rate limits for the Companies House tab. Get one at{' '}
        <a
          href="https://developer.company-information.service.gov.uk/"
          target="_blank"
          rel="noreferrer"
          className="text-accent hover:underline"
        >
          developer.company-information.service.gov.uk
        </a>
        .
      </p>
      <div className="space-y-4 bg-surface-card border border-slate-200 rounded-xl p-4 shadow-sm">
        <div>
          <label className="block text-sm text-ink-muted mb-1">API key</label>
          <input
            type="password"
            value={config.companiesHouse.apiKey}
            onChange={(e) => setCompaniesHouseConfig({ apiKey: e.target.value })}
            placeholder="Optional"
            autoComplete="off"
            className="w-full px-4 py-2 bg-surface-muted border border-slate-200 rounded-lg text-ink text-sm"
          />
        </div>
      </div>
    </section>
  );
};
