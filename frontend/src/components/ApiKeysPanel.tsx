/**
 * All browser-stored API keys in one panel — used only on About.
 */
import React from 'react';
import { KeyRound } from 'lucide-react';
import { LlmCredentialsSection } from './LlmCredentialsSection';
import { CompaniesHouseApiKeySection } from './CompaniesHouseApiKeySection';
import { ScreeningApiKeySection } from './ScreeningApiKeySection';

export const ApiKeysPanel: React.FC = () => {
  return (
    <div id="api-keys" className="space-y-10 scroll-mt-4">
      <div className="flex items-center gap-3 mb-2">
        <div className="bg-accent p-2 rounded-xl shadow-sm">
          <KeyRound className="w-6 h-6 text-white" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-ink">API keys</h2>
          <p className="text-sm text-ink-muted">
            One place for credentials used across Chat, Entity Extractor, Companies House, and Name screening. Mirror LLM
            keys on the backend for server-side RAG (
            <code className="bg-surface-muted px-1 rounded text-xs">OPENROUTER_API_KEY</code> / OpenAI). Screening keys
            can also live only in server <code className="bg-surface-muted px-1 rounded text-xs">.env</code>.
          </p>
        </div>
      </div>
      <LlmCredentialsSection title="LLM (OpenRouter / OpenAI)" />
      <CompaniesHouseApiKeySection />
      <ScreeningApiKeySection />
    </div>
  );
};
