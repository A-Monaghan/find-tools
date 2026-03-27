/**
 * Entity Extractor > Settings — extraction system prompt (EE-only), Neo4j. LLM keys and model live in About / header.
 */
import React from 'react';
import { Settings, Database } from 'lucide-react';
import { useUnifiedConfig, DEFAULT_ENTITY_EXTRACTOR_SYSTEM_PROMPT } from '../context/UnifiedConfigContext';

export const EntityExtractorSettings: React.FC = () => {
  const { config, setEntityExtractorConfig } = useUnifiedConfig();
  const ee = config.entityExtractor;

  return (
    <div className="h-full overflow-y-auto p-6 sm:p-10 custom-scrollbar">
      <div className="max-w-2xl mx-auto space-y-8">
        <div className="flex items-center gap-3 mb-6">
          <div className="bg-accent p-2 rounded-xl">
            <Settings className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-xl font-bold text-ink">Entity Extractor Settings</h1>
        </div>

        <p className="text-sm text-ink-muted -mt-4">
          <strong className="text-ink">API keys</strong> and <strong className="text-ink">model</strong> are shared with Chat: configure keys on{' '}
          <strong className="text-ink">About</strong>, choose the model in the <strong className="text-ink">header</strong> (top right).
        </p>

        {/* System prompt — Entity Extractor only (rag_config_entity_extractor); Chat prompts are separate) */}
        <section>
          <h2 className="text-lg font-semibold text-ink mb-3">System prompt template</h2>
          <p className="text-ink-muted text-xs mb-2">
            <strong className="text-ink">Entity Extractor only</strong> — not sent to RAG Chat or other tools. Stored under{' '}
            <code className="bg-surface-muted px-1 rounded text-xs">rag_config_entity_extractor</code>, separate from Chat{' '}
            <code className="bg-surface-muted px-1 rounded text-xs">rag_config_chat</code>. Edit the OSINT extraction instructions below; reset restores
            the built-in default.
          </p>
          <div className="flex flex-wrap gap-2 mb-3">
            <button
              type="button"
              onClick={() => setEntityExtractorConfig({ systemPromptTemplate: DEFAULT_ENTITY_EXTRACTOR_SYSTEM_PROMPT })}
              className="px-3 py-1.5 text-xs font-medium rounded-lg bg-surface-muted text-ink hover:bg-slate-200 border border-slate-200"
            >
              Reset to Entity Extractor default
            </button>
          </div>
          <textarea
            value={ee.systemPromptTemplate}
            onChange={(e) => setEntityExtractorConfig({ systemPromptTemplate: e.target.value })}
            rows={18}
            className="w-full px-4 py-3 bg-surface-muted border border-slate-200 rounded-xl text-ink text-sm font-mono resize-y focus:outline-none focus:ring-2 focus:ring-accent/50"
            spellCheck
          />
        </section>

        {/* Neo4j */}
        <section>
          <h2 className="text-lg font-semibold text-ink mb-3 flex items-center gap-2">
            <Database className="w-5 h-5 text-accent" />
            Neo4j
          </h2>
          <div className="space-y-4 bg-surface-card border border-slate-200 rounded-xl p-4 shadow-sm">
            <div>
              <label className="block text-sm text-ink-muted mb-1">URI</label>
              <input
                type="text"
                value={ee.neo4jUri}
                onChange={(e) => setEntityExtractorConfig({ neo4jUri: e.target.value })}
                placeholder="bolt://localhost:7687"
                className="w-full px-4 py-2 bg-surface-muted border border-slate-200 rounded-lg text-ink text-sm"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-ink-muted mb-1">Username</label>
                <input
                  type="text"
                  value={ee.neo4jUsername}
                  onChange={(e) => setEntityExtractorConfig({ neo4jUsername: e.target.value })}
                  className="w-full px-4 py-2 bg-surface-muted border border-slate-200 rounded-lg text-ink text-sm"
                />
              </div>
              <div>
                <label className="block text-sm text-ink-muted mb-1">Password</label>
                <input
                  type="password"
                  value={ee.neo4jPassword}
                  onChange={(e) => setEntityExtractorConfig({ neo4jPassword: e.target.value })}
                  className="w-full px-4 py-2 bg-surface-muted border border-slate-200 rounded-lg text-ink text-sm"
                />
              </div>
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={ee.autoPushNeo4j}
                onChange={(e) => setEntityExtractorConfig({ autoPushNeo4j: e.target.checked })}
                className="rounded text-indigo-500"
              />
              <span className="text-ink text-sm">Auto-push to Neo4j after extraction</span>
            </label>
          </div>
        </section>
      </div>
    </div>
  );
};
