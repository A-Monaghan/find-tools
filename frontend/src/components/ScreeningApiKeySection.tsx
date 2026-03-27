/**
 * OpenSanctions / Aleph / Sayari credentials — browser localStorage, sent with each screening request.
 * Server .env keys are still used when these are empty (shared deployments).
 */
import React from 'react';
import { Fingerprint } from 'lucide-react';
import { useUnifiedConfig } from '../context/UnifiedConfigContext';

type Props = {
  /** When true, show shorter intro (e.g. embedded on Name screening tab) */
  compact?: boolean;
};

export const ScreeningApiKeySection: React.FC<Props> = ({ compact }) => {
  const { config, setScreeningConfig } = useUnifiedConfig();
  const s = config.screening;

  const inputClass =
    'w-full px-4 py-2 bg-surface-muted border border-slate-200 rounded-lg text-ink text-sm';

  return (
    <section id="api-keys-screening" className="scroll-mt-4">
      <h2 className="text-lg font-semibold text-ink mb-3 flex items-center gap-2">
        <Fingerprint className="w-5 h-5 text-accent" />
        Name screening API keys
      </h2>
      {!compact && (
        <p className="text-sm text-ink-muted mb-3">
          Optional. Enter keys here to run OpenSanctions, Aleph, and Sayari from your browser session. If a field is
          empty, the backend falls back to server environment variables (when set). Keys are stored only in this
          browser (localStorage), not on the server disk.
        </p>
      )}
      {compact && (
        <p className="text-xs text-ink-muted mb-3">
          Stored in this browser only. Leave blank to use server <span className="font-mono">.env</span> only.
        </p>
      )}
      <div className="space-y-4 bg-surface-card border border-slate-200 rounded-xl p-4 shadow-sm">
        <div>
          <label className="block text-sm text-ink-muted mb-1">OpenSanctions API key</label>
          <input
            type="password"
            value={s.openSanctionsApiKey}
            onChange={(e) => setScreeningConfig({ openSanctionsApiKey: e.target.value })}
            placeholder="ApiKey from opensanctions.org/api"
            autoComplete="off"
            className={inputClass}
          />
        </div>
        <div>
          <label className="block text-sm text-ink-muted mb-1">Aleph API key</label>
          <input
            type="password"
            value={s.alephApiKey}
            onChange={(e) => setScreeningConfig({ alephApiKey: e.target.value })}
            placeholder="OCCRP Aleph Pro API key"
            autoComplete="off"
            className={inputClass}
          />
        </div>
        <div>
          <label className="block text-sm text-ink-muted mb-1">Aleph API base (optional)</label>
          <input
            type="text"
            value={s.alephApiBase}
            onChange={(e) => setScreeningConfig({ alephApiBase: e.target.value })}
            placeholder="https://aleph.occrp.org/api/2"
            autoComplete="off"
            className={inputClass}
          />
        </div>
        <div className="border-t border-slate-100 pt-4">
          <p className="text-xs font-medium text-ink mb-2">Sayari (OAuth client credentials)</p>
          <div className="space-y-3">
            <div>
              <label className="block text-sm text-ink-muted mb-1">Client ID</label>
              <input
                type="password"
                value={s.sayariClientId}
                onChange={(e) => setScreeningConfig({ sayariClientId: e.target.value })}
                placeholder="Client ID"
                autoComplete="off"
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-sm text-ink-muted mb-1">Client secret</label>
              <input
                type="password"
                value={s.sayariClientSecret}
                onChange={(e) => setScreeningConfig({ sayariClientSecret: e.target.value })}
                placeholder="Client secret"
                autoComplete="off"
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-sm text-ink-muted mb-1">Sayari API base (optional)</label>
              <input
                type="text"
                value={s.sayariApiBase}
                onChange={(e) => setScreeningConfig({ sayariApiBase: e.target.value })}
                placeholder="https://api.sayari.com"
                autoComplete="off"
                className={inputClass}
              />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
