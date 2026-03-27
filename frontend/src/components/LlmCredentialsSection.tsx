/**
 * OpenRouter / OpenAI credentials — rendered from About (ApiKeysPanel) only.
 */
import React from 'react';
import { KeyRound } from 'lucide-react';
import { useUnifiedConfig } from '../context/UnifiedConfigContext';

export const LlmCredentialsSection: React.FC<{ title?: string }> = ({
  title = 'LLM API (OpenRouter / OpenAI)',
}) => {
  const { config, setLlmConfig } = useUnifiedConfig();
  const llm = config.llm;

  return (
    <section id="api-keys-llm" className="scroll-mt-4">
      <h2 className="text-lg font-semibold text-ink mb-3 flex items-center gap-2">
        <KeyRound className="w-5 h-5 text-accent" />
        {title}
      </h2>
      <p className="text-sm text-ink-muted mb-3">
        <strong className="text-ink">Entity Extractor</strong> sends these from the browser. <strong className="text-ink">Chat</strong>{' '}
        uses keys configured on the API server — add the same values to your backend <code className="bg-surface-muted px-1 rounded text-xs">.env</code>{' '}
        so RAG completions work.
      </p>
      <div className="flex gap-4 mb-4">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="radio"
            checked={llm.provider === 'openrouter'}
            onChange={() => setLlmConfig({ provider: 'openrouter' })}
            className="text-accent"
          />
          <span className="text-ink">OpenRouter</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="radio"
            checked={llm.provider === 'openai'}
            onChange={() => setLlmConfig({ provider: 'openai' })}
            className="text-accent"
          />
          <span className="text-ink">OpenAI</span>
        </label>
      </div>
      <div className="space-y-4 bg-surface-card border border-slate-200 rounded-xl p-4 shadow-sm">
        <div>
          <label className="block text-sm text-ink-muted mb-1">OpenRouter API key</label>
          <input
            type="password"
            value={llm.openRouterApiKey}
            onChange={(e) => setLlmConfig({ openRouterApiKey: e.target.value })}
            placeholder="sk-or-..."
            autoComplete="off"
            className="w-full px-4 py-2 bg-surface-muted border border-slate-200 rounded-lg text-ink text-sm"
          />
        </div>
        <div>
          <label className="block text-sm text-ink-muted mb-1">OpenAI API key</label>
          <input
            type="password"
            value={llm.openaiApiKey}
            onChange={(e) => setLlmConfig({ openaiApiKey: e.target.value })}
            placeholder="sk-..."
            autoComplete="off"
            className="w-full px-4 py-2 bg-surface-muted border border-slate-200 rounded-lg text-ink text-sm"
          />
        </div>
      </div>
      <p className="text-xs text-ink-muted mt-2">
        Model for chat and extraction is chosen in the <strong className="text-ink">header</strong> (top right), not here.
      </p>
    </section>
  );
};
