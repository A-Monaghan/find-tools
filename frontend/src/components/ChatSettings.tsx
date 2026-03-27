/**
 * Chat > Settings — researcher profile, prompt, query pass (model = header only).
 */
import React from 'react';
import { Settings, Zap } from 'lucide-react';
import { useUnifiedConfig, DEFAULT_RESEARCHER_PROFILE } from '../context/UnifiedConfigContext';

const PROMPT_TEMPLATES: { id: string; label: string; value: string }[] = [
  {
    id: 'default',
    label: 'Default',
    value: `INSTRUCTIONS:
1. Answer ONLY using the information in the provided context
2. If the answer is not in the context, respond: "The information is not found in the provided documents."
3. Cite your sources using [1], [2], etc. referring to the context numbers
4. Be concise but thorough
5. Use markdown formatting for clarity

CONTEXT:
{context}

Answer the following question based ONLY on the context above.`,
  },
  {
    id: 'investigative',
    label: 'Investigative',
    value: `INSTRUCTIONS:
1. Extract factual information, relationships, timelines, and patterns from the provided context
2. Identify key entities: people, organisations, locations, dates, events, and connections
3. Highlight inconsistencies, gaps, or areas requiring further investigation
4. Cite sources using [1], [2], etc. with page references where available
5. Distinguish between verified facts and inferences
6. Use structured formatting: bullet points, timelines, and relationship notes where appropriate

CONTEXT:
{context}

Answer based ONLY on the information above.`,
  },
  {
    id: 'analytical',
    label: 'Analytical',
    value: `INSTRUCTIONS:
1. Provide comprehensive analysis with multiple perspectives
2. Identify underlying themes, patterns, and connections across sources
3. Compare and contrast different viewpoints or findings
4. Highlight implications, consequences, and broader significance
5. Cite sources using [1], [2], etc. with specific page references
6. Structure your response with clear sections and subsections
7. Use markdown formatting: headers, lists, tables, and emphasis

CONTEXT:
{context}

Provide a thorough analytical response based ONLY on the information above.`,
  },
];

interface ChatSettingsProps {
  /** OpenRouter id from API (OPENROUTER_FAST_MODEL); shown for Draft mode copy */
  fastModelId?: string;
}

export const ChatSettings: React.FC<ChatSettingsProps> = ({ fastModelId }) => {
  const { config, setChatConfig } = useUnifiedConfig();

  return (
    <div className="h-full overflow-y-auto p-6 sm:p-10 custom-scrollbar">
      <div className="max-w-2xl mx-auto space-y-8">
        <div className="flex items-center gap-3 mb-6">
          <div className="bg-accent p-2 rounded-xl">
            <Settings className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-xl font-bold text-ink">Chat Settings</h1>
        </div>

        <p className="text-sm text-ink-muted -mt-4">
          <strong className="text-ink">Model</strong> is selected in the header (top right). <strong className="text-ink">API keys</strong> are on the{' '}
          <strong className="text-ink">About</strong> tab.
        </p>

        {/* Pass mode: full-quality model vs fast draft */}
        <section>
          <h2 className="text-lg font-semibold text-ink mb-3 flex items-center gap-2">
            <Zap className="w-5 h-5 text-accent" />
            Query pass
          </h2>
          <div className="bg-surface-card border border-slate-200 rounded-xl p-4 space-y-3 shadow-sm">
            <p className="text-sm text-ink-muted">
              <strong className="text-ink">Research</strong> uses the model selected in the header.{' '}
              <strong className="text-ink">Draft</strong> uses the server&apos;s fast model for quicker, cheaper turns (
              {fastModelId ? (
                <code className="bg-surface-muted px-1 rounded text-xs">{fastModelId}</code>
              ) : (
                'load models to see id'
              )}
              ).
            </p>
            <div className="flex flex-wrap gap-2">
              {(['research', 'draft'] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setChatConfig({ passMode: mode })}
                  className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
                    config.chat.passMode === mode
                      ? 'border-accent bg-accent text-white'
                      : 'border-slate-200 bg-surface-muted text-ink hover:border-slate-300'
                  }`}
                >
                  {mode === 'draft' ? 'Draft (fast)' : 'Research'}
                </button>
              ))}
            </div>
          </div>
        </section>

        {/* Researcher profile — prepended to the full system prompt */}
        <section>
          <h2 className="text-lg font-semibold text-ink mb-3">Researcher profile</h2>
          <p className="text-ink-muted text-xs mb-2">
            Describes <strong className="text-ink">who the assistant is</strong> and your research standards. This is sent{' '}
            <em>before</em> the prompt template below (with <code className="bg-surface-muted px-1 rounded text-accent">{'{context}'}</code>).
          </p>
          <div className="flex flex-wrap gap-2 mb-3">
            <button
              type="button"
              onClick={() => setChatConfig({ researcherProfile: DEFAULT_RESEARCHER_PROFILE })}
              className="px-3 py-1.5 text-xs font-medium rounded-lg bg-surface-muted text-ink hover:bg-slate-200 border border-slate-200"
            >
              Reset to default
            </button>
          </div>
          <textarea
            value={config.chat.researcherProfile}
            onChange={(e) => setChatConfig({ researcherProfile: e.target.value })}
            rows={5}
            className="w-full px-4 py-3 bg-surface-muted border border-slate-200 rounded-xl text-ink text-sm resize-y focus:outline-none focus:ring-2 focus:ring-accent/50"
            placeholder="Researcher profile..."
            spellCheck
          />
        </section>

        {/* System prompt template */}
        <section>
          <h2 className="text-lg font-semibold text-ink mb-3">System prompt template</h2>
          <p className="text-ink-muted text-xs mb-2">
            Use <code className="bg-surface-muted px-1 rounded text-accent">{'{context}'}</code> where document text is inserted.
          </p>
          <div className="flex flex-wrap gap-2 mb-3">
            {PROMPT_TEMPLATES.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setChatConfig({ customPrompt: t.value })}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                  config.chat.customPrompt === t.value
                    ? 'bg-accent text-white'
                    : 'bg-surface-muted text-ink hover:bg-slate-200 border border-slate-200'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <textarea
            value={config.chat.customPrompt}
            onChange={(e) => setChatConfig({ customPrompt: e.target.value })}
            rows={12}
            className="w-full px-4 py-3 bg-surface-muted border border-slate-200 rounded-xl text-ink text-sm font-mono resize-y focus:outline-none focus:ring-2 focus:ring-accent/50"
            placeholder="System prompt template..."
            spellCheck={false}
          />
        </section>
      </div>
    </div>
  );
};
