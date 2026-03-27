/**
 * Entity Extractor — extracts entities/relationships from URL or text via OOCP.
 * Uses unified config for provider, API keys, Neo4j. Prompts fetched from OOCP.
 */
import React, { useState, useCallback, useEffect, useMemo } from 'react';
import { Link, FileText, XCircle, Database } from 'lucide-react';
import {
  analyzeWithBackendStreaming,
  fetchPromptDefaults,
  pushToNeo4j,
} from '../services/entityExtractorService';
import { downloadCsv, downloadJson } from '../utils/csvHelper';
import DataTable from './DataTable';
import Spinner from './Spinner';
import { useUnifiedConfig, DEFAULT_ENTITY_EXTRACTOR_SYSTEM_PROMPT } from '../context/UnifiedConfigContext';
import { loadDraftValue, saveDraftValue } from '../utils/draftState';
import { normalizeModelIdForProvider } from '../utils/modelId';

interface Entity {
  id: string;
  name: string;
  label: string;
}

interface Relationship {
  id: string;
  source: string;
  target: string;
  type: string;
}

const FALLBACK_USER_TEMPLATE = `Analyze the following text and extract entities and relationships. Return the result as a JSON object with the following structure:
{
    "entities": [
        {"name": "entity name", "label": "entity type"}
    ],
    "relationships": [
        {"source": "source entity name", "target": "target entity name", "type": "relationship type"}
    ]
}

Guidelines:
- Extract named entities (people, organizations, locations, concepts, etc.)
- Identify relationships between entities
- Use clear, descriptive labels for entities
- Use meaningful relationship types
- Return only valid JSON

Text to analyze:
__TEXT_TO_ANALYZE__

Return only the JSON object, no additional text.`;
const EE_DRAFT_PREFIX = 'rag_v2_draft_entity_';

export const EntityExtractor: React.FC = () => {
  const { config } = useUnifiedConfig();
  const ee = config.entityExtractor;
  const llm = config.llm;
  // Keep model id compatible with selected provider to avoid backend 500s.
  const resolveExtractionModel = useCallback(() => {
    return normalizeModelIdForProvider(config.chat.selectedModelId, llm.provider);
  }, [config.chat.selectedModelId, llm.provider]);

  const [inputMode, setInputMode] = useState<'url' | 'text'>(() =>
    loadDraftValue(`${EE_DRAFT_PREFIX}input_mode`, 'url') === 'text' ? 'text' : 'url'
  );
  const [url, setUrl] = useState(() => loadDraftValue(`${EE_DRAFT_PREFIX}url`));
  const [text, setText] = useState(() => loadDraftValue(`${EE_DRAFT_PREFIX}text`));
  const [entities, setEntities] = useState<Entity[]>([]);
  const [relationships, setRelationships] = useState<Relationship[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [progressLog, setProgressLog] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [chunkingMethod, setChunkingMethod] = useState(() =>
    loadDraftValue(`${EE_DRAFT_PREFIX}chunking`, 'auto')
  );
  const [extractionMethod, setExtractionMethod] = useState(() =>
    loadDraftValue(`${EE_DRAFT_PREFIX}extraction`, 'quality')
  );
  // OOCP /api/prompt-defaults system_prompt; EE Settings systemPromptTemplate is separate from Chat
  const [backendSystemPrompt, setBackendSystemPrompt] = useState(DEFAULT_ENTITY_EXTRACTOR_SYSTEM_PROMPT);
  const [userPromptTemplate, setUserPromptTemplate] = useState(FALLBACK_USER_TEMPLATE);
  const effectiveSystemPrompt = useMemo(
    () => ee.systemPromptTemplate.trim() || backendSystemPrompt,
    [ee.systemPromptTemplate, backendSystemPrompt]
  );
  const [pushStatus, setPushStatus] = useState<string | null>(null);

  useEffect(() => {
    fetchPromptDefaults()
      .then((d) => {
        setBackendSystemPrompt(d.system_prompt);
        setUserPromptTemplate(d.user_prompt_template);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    saveDraftValue(`${EE_DRAFT_PREFIX}input_mode`, inputMode);
  }, [inputMode]);
  useEffect(() => {
    saveDraftValue(`${EE_DRAFT_PREFIX}url`, url);
  }, [url]);
  useEffect(() => {
    saveDraftValue(`${EE_DRAFT_PREFIX}text`, text);
  }, [text]);
  useEffect(() => {
    saveDraftValue(`${EE_DRAFT_PREFIX}chunking`, chunkingMethod);
  }, [chunkingMethod]);
  useEffect(() => {
    saveDraftValue(`${EE_DRAFT_PREFIX}extraction`, extractionMethod);
  }, [extractionMethod]);

  const normalizeId = (name: string) => name.replace(/\s+/g, '_').toLowerCase();

  const processGraphResults = useCallback(
    ({
      entities: rawEntities,
      relationships: rawRelationships,
    }: {
      entities: { name: string; label: string }[];
      relationships: { source: string; target: string; type: string }[];
    }) => {
      const entityMap = new Map<string, Entity>();
      rawEntities.forEach((rawEntity) => {
        const id = normalizeId(rawEntity.name);
        if (!entityMap.has(id)) {
          entityMap.set(id, { ...rawEntity, id });
        }
      });
      const updatedEntities = Array.from(entityMap.values());

      const relationshipMap = new Map<string, Relationship>();
      rawRelationships.forEach((rawRel) => {
        const sourceId = normalizeId(rawRel.source);
        const targetId = normalizeId(rawRel.target);
        if (entityMap.has(sourceId) && entityMap.has(targetId)) {
          const relId = `${sourceId}_${normalizeId(rawRel.type)}_${targetId}`;
          if (!relationshipMap.has(relId)) {
            relationshipMap.set(relId, {
              id: relId,
              source: sourceId,
              target: targetId,
              type: rawRel.type.toUpperCase().replace(/\s+/g, '_'),
            });
          }
        }
      });
      setEntities(updatedEntities);
      setRelationships(Array.from(relationshipMap.values()));
    },
    []
  );

  const handleAnalyze = useCallback(async () => {
    if (inputMode === 'url' && (!url.trim() || !/^(http|https)s?:\/\//.test(url))) {
      setError('Please enter a valid URL (e.g., https://...).');
      return;
    }
    if (inputMode === 'text' && !text.trim()) {
      setError('Please enter text to analyze.');
      return;
    }
    const apiKey = llm.provider === 'openai' ? llm.openaiApiKey : llm.openRouterApiKey;
    if (!apiKey.trim()) {
      setError(
        `${llm.provider === 'openai' ? 'OpenAI' : 'OpenRouter'} API key required. Add it under About → API keys.`
      );
      return;
    }
    setIsLoading(true);
    setError(null);
    setProgressLog([]);
    setEntities([]);
    setRelationships([]);

    try {
      const twoPass = extractionMethod === 'quality' || extractionMethod === 'ftm';
      const extractionModel = resolveExtractionModel();
      const response = await analyzeWithBackendStreaming(
        {
          model_type: llm.provider,
          api_key: llm.provider === 'openrouter' ? llm.openRouterApiKey.trim() : undefined,
          openai_api_key: llm.provider === 'openai' ? llm.openaiApiKey.trim() : undefined,
          openrouter_model: llm.provider === 'openrouter' ? extractionModel : undefined,
          openai_model: llm.provider === 'openai' ? extractionModel : undefined,
          input_mode: inputMode,
          two_pass: twoPass,
          extraction_method: extractionMethod === 'ftm' ? 'ftm' : null,
          chunking_method: chunkingMethod === 'auto' ? null : chunkingMethod,
          ...(inputMode === 'url' ? { url: url.trim() } : { text: text.trim() }),
          system_prompt: effectiveSystemPrompt.trim() || null,
          user_prompt_template: userPromptTemplate.trim() || null,
        },
        (p) => {
          if (p.message) setProgressLog((prev) => [...prev, p.message as string]);
        }
      );
      if (response.extracted_text) setText(response.extracted_text);
      processGraphResults(response.data);
      // Auto-push to Neo4j if enabled and connection configured
      if (ee.autoPushNeo4j && ee.neo4jUri.trim() && ee.neo4jPassword.trim()) {
        const { entities: rawE, relationships: rawR } = response.data;
        const entityMap = new Map<string, Entity>();
        rawE.forEach((re) => {
          const id = normalizeId(re.name);
          entityMap.set(id, { ...re, id });
        });
        const rels = rawR
          .filter((r) => entityMap.has(normalizeId(r.source)) && entityMap.has(normalizeId(r.target)))
          .map((r) => ({
            id: `${normalizeId(r.source)}_${normalizeId(r.type)}_${normalizeId(r.target)}`,
            source: normalizeId(r.source),
            target: normalizeId(r.target),
            type: r.type.toUpperCase().replace(/\s+/g, '_'),
          }));
        try {
          const connection = {
            uri: ee.neo4jUri.trim(),
            username: ee.neo4jUsername.trim() || 'neo4j',
            password: ee.neo4jPassword.trim(),
          };
          const res = await pushToNeo4j(Array.from(entityMap.values()), rels, connection);
          setPushStatus(`Auto-pushed: ${res.nodes_created} nodes, ${res.relationships_created} relationships.`);
        } catch (e) {
          setPushStatus(`Auto-push failed: ${e instanceof Error ? e.message : 'Unknown'}`);
        }
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'An unexpected error occurred.');
    } finally {
      setIsLoading(false);
      setProgressLog([]);
    }
  }, [
    url,
    text,
    inputMode,
    extractionMethod,
    chunkingMethod,
    effectiveSystemPrompt,
    userPromptTemplate,
    processGraphResults,
    ee,
    llm,
    resolveExtractionModel,
  ]);

  const clearAll = () => {
    setUrl('');
    setText('');
    setEntities([]);
    setRelationships([]);
    setError(null);
    setProgressLog([]);
    setIsLoading(false);
  };

  const handleDownloadEntities = (format: 'csv' | 'json') => {
    if (format === 'csv') {
      downloadCsv(
        entities.map((e) => ({ 'entityId:ID': e.id, name: e.name, ':LABEL': e.label })),
        'entities.csv'
      );
    } else {
      downloadJson(entities.map((e) => ({ id: e.id, name: e.name, label: e.label })), 'entities.json');
    }
  };

  const handleDownloadRelationships = (format: 'csv' | 'json') => {
    if (format === 'csv') {
      downloadCsv(
        relationships.map((r) => ({ ':START_ID': r.source, ':END_ID': r.target, ':TYPE': r.type })),
        'relationships.csv'
      );
    } else {
      downloadJson(
        relationships.map((r) => ({ source: r.source, target: r.target, type: r.type })),
        'relationships.json'
      );
    }
  };

  const handlePushToNeo4j = useCallback(async () => {
    if (entities.length === 0 && relationships.length === 0) return;
    if (!ee.neo4jUri.trim() || !ee.neo4jPassword.trim()) {
      setPushStatus('Error: Neo4j URI and password required. Configure connection below.');
      return;
    }
    setPushStatus(null);
    try {
      const connection = {
        uri: ee.neo4jUri.trim(),
        username: ee.neo4jUsername.trim() || 'neo4j',
        password: ee.neo4jPassword.trim(),
      };
      const res = await pushToNeo4j(entities, relationships, connection);
      setPushStatus(`Pushed ${res.nodes_created} nodes, ${res.relationships_created} relationships.`);
    } catch (e: unknown) {
      setPushStatus(`Error: ${e instanceof Error ? e.message : 'Unknown'}`);
    }
  }, [entities, relationships, ee]);

  const hasResults = entities.length > 0 || relationships.length > 0;

  const apiKey = llm.provider === 'openai' ? llm.openaiApiKey : llm.openRouterApiKey;
  const needsConfig = !apiKey.trim();

  return (
    <div className="flex h-full">
      <div className="flex-1 flex flex-col h-full">
        <div className="flex-1 overflow-hidden relative">
          <div className="h-full overflow-y-auto p-6 sm:p-10 custom-scrollbar">
            <div className="max-w-4xl mx-auto">
              <div className="p-4 sm:p-6 rounded-xl bg-surface-card border border-slate-200 shadow-sm">
                {needsConfig && (
                  <div className="mb-4 p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-sm">
                    Configure API key under About → API keys.
                  </div>
                )}
                <div className="flex border-b border-slate-200 mb-4 gap-2">
                      <button
                        onClick={() => setInputMode('url')}
                        className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all ${
                          inputMode === 'url'
                            ? 'bg-accent text-white shadow-sm'
                            : 'text-ink-muted hover:text-ink hover:bg-slate-100'
                        }`}
                      >
                        Analyze from URL
                      </button>
                      <button
                        onClick={() => setInputMode('text')}
                        className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all ${
                          inputMode === 'text'
                            ? 'bg-accent text-white shadow-sm'
                            : 'text-ink-muted hover:text-ink hover:bg-slate-100'
                        }`}
                      >
                        Analyze from Text
                      </button>
                    </div>

                    {inputMode === 'url' ? (
                      <div>
                        <label className="block text-[10px] font-bold uppercase tracking-widest text-ink-muted mb-1">
                          Website URL
                        </label>
                        <input
                          type="url"
                          value={url}
                          onChange={(e) => setUrl(e.target.value)}
                          placeholder="https://example.com/article"
                          className="w-full px-4 py-3 bg-surface-muted border border-slate-200 rounded-xl text-ink text-sm focus:outline-none focus:ring-2 focus:ring-accent/50 placeholder-ink-subtle"
                        />
                      </div>
                    ) : (
                      <div>
                        <label className="block text-[10px] font-bold uppercase tracking-widest text-ink-muted mb-1">
                          Text Content
                        </label>
                        <textarea
                          value={text}
                          onChange={(e) => setText(e.target.value)}
                          placeholder="Paste your text here..."
                          rows={8}
                          className="w-full px-4 py-3 bg-surface-muted border border-slate-200 rounded-xl text-ink text-sm font-mono resize-y focus:outline-none focus:ring-2 focus:ring-accent/50 placeholder-ink-subtle"
                        />
                      </div>
                    )}

                    <div className="mt-4 flex flex-wrap items-center gap-4">
                      <div className="flex items-center gap-2">
                        <label className="text-xs font-bold uppercase tracking-widest text-ink-muted">
                          Chunking
                        </label>
                        <select
                          value={chunkingMethod}
                          onChange={(e) => setChunkingMethod(e.target.value)}
                          className="px-3 py-2 rounded-lg bg-surface-muted border border-slate-200 text-ink text-sm"
                        >
                          <option value="auto">Auto</option>
                          <option value="docling">Docling Hybrid</option>
                          <option value="sliding">Sliding Window</option>
                          <option value="character">Character Split</option>
                        </select>
                      </div>
                      <div className="flex items-center gap-2">
                        <label className="text-xs font-bold uppercase tracking-widest text-slate-500">
                          Extraction
                        </label>
                        <select
                          value={extractionMethod}
                          onChange={(e) => setExtractionMethod(e.target.value)}
                          className="px-3 py-2 rounded-lg bg-surface-muted border border-slate-200 text-ink text-sm"
                        >
                          <option value="quality">Two-Pass (Quality)</option>
                          <option value="fast">Single-Pass (Fast)</option>
                          <option value="ftm">FTM Schema-Guided</option>
                        </select>
                      </div>
                      <button
                        onClick={handleAnalyze}
                        disabled={isLoading}
                        className="flex items-center gap-2 bg-accent hover:bg-accent-hover px-4 py-2.5 rounded-xl text-white text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {isLoading ? (
                          <Spinner />
                        ) : inputMode === 'url' ? (
                          <Link className="w-5 h-5" />
                        ) : (
                          <FileText className="w-5 h-5" />
                        )}
                        {isLoading ? 'Analyzing...' : inputMode === 'url' ? 'Fetch & Analyze' : 'Extract Relationships'}
                      </button>
                      <button
                        onClick={clearAll}
                        className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-ink-muted hover:text-ink hover:bg-slate-100 text-sm font-semibold"
                      >
                        <XCircle className="w-5 h-5" /> Clear All
                      </button>
                    </div>
                    {progressLog.length > 0 && (
                      <div className="mt-3 px-3 py-2 rounded-lg bg-accent-light border border-accent/30 text-sm text-accent font-mono overflow-y-auto max-h-20">
                        {progressLog.map((line, i) => (
                          <div key={i}>{line}</div>
                        ))}
                      </div>
                    )}
                  </div>

                  {error && (
                    <div className="mt-6 p-4 rounded-xl bg-red-500/10 border border-red-500/30" role="alert">
                      <p className="font-bold text-red-400">Error</p>
                      <p className="text-sm text-ink-muted mt-1">{error}</p>
                    </div>
                  )}

                  {pushStatus && (
                    <div className="mt-4 p-3 rounded-xl bg-surface-muted border border-slate-200 text-sm text-ink">
                      {pushStatus}
                    </div>
                  )}

                  {hasResults && (
                    <div className="mt-8 space-y-8">
                      <div className="flex flex-wrap gap-3 items-center justify-between mb-4">
                        <span className="text-sm text-ink-muted">
                          Neo4j configured in Settings. Auto-push: {ee.autoPushNeo4j ? 'on' : 'off'}
                        </span>
                        <button
                          onClick={handlePushToNeo4j}
                          disabled={!ee.neo4jUri.trim() || !ee.neo4jPassword.trim()}
                          className="inline-flex items-center gap-2 px-4 py-2.5 bg-accent hover:bg-accent-hover border border-accent/50 rounded-xl text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <Database className="w-3.5 h-3.5" /> Push to Neo4j
                        </button>
                      </div>
                      <div>
                        <div className="flex justify-between items-center mb-2">
                          <h2 className="text-xl font-bold text-ink">Entities ({entities.length})</h2>
                          <div className="flex gap-2">
                            <button
                              onClick={() => handleDownloadEntities('csv')}
                              className="px-3 py-1.5 bg-surface-muted border border-slate-200 rounded-lg text-ink hover:bg-slate-200 text-xs font-medium"
                            >
                              CSV
                            </button>
                            <button
                              onClick={() => handleDownloadEntities('json')}
                              className="px-3 py-1.5 bg-surface-muted border border-slate-200 rounded-lg text-ink hover:bg-slate-200 text-xs font-medium"
                            >
                              JSON
                            </button>
                          </div>
                        </div>
                        <div className="rounded-xl bg-surface-muted border border-slate-200 overflow-hidden">
                          <DataTable
                            headers={['ID', 'Name', 'Label']}
                            data={entities.map((e) => [e.id, e.name, e.label])}
                          />
                        </div>
                      </div>
                      <div>
                        <div className="flex justify-between items-center mb-2">
                          <h2 className="text-xl font-bold text-ink">
                            Relationships ({relationships.length})
                          </h2>
                          <div className="flex gap-2">
                            <button
                              onClick={() => handleDownloadRelationships('csv')}
                              className="px-3 py-1.5 bg-surface-muted border border-slate-200 rounded-lg text-ink hover:bg-slate-200 text-xs font-medium"
                            >
                              CSV
                            </button>
                            <button
                              onClick={() => handleDownloadRelationships('json')}
                              className="px-3 py-1.5 bg-surface-muted border border-slate-200 rounded-lg text-ink hover:bg-slate-200 text-xs font-medium"
                            >
                              JSON
                            </button>
                          </div>
                        </div>
                        <div className="rounded-xl bg-surface-muted border border-slate-200 overflow-hidden">
                          <DataTable
                            headers={['Source', 'Target', 'Type']}
                            data={relationships.map((r) => [r.source, r.target, r.type])}
                          />
                        </div>
                      </div>
                    </div>
                  )}
              </div>
            </div>
          </div>
        </div>
      </div>
  );
};
