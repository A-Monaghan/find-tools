import React, { useState, useCallback, useEffect } from 'react';
import { Entity, Relationship, RawEntity, RawRelationship } from './types';
import { analyzeWithBackend, fetchPromptDefaults } from './services/backendAnalysisService';
import { downloadCsv } from './utils/csvHelper';
import DataTable from './components/DataTable';
import Spinner from './components/Spinner';
import { Icon } from './components/Icon';
const FALLBACK_SYSTEM_PROMPT = 'You are a helpful assistant that extracts entities and relationships from text. Always respond with valid JSON.';
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

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'analyze' | 'about'>('analyze');
  const [inputMode, setInputMode] = useState<'url' | 'text'>('url');
  const [url, setUrl] = useState<string>('');
  const [text, setText] = useState<string>('');
  const [entities, setEntities] = useState<Entity[]>([]);
  const [relationships, setRelationships] = useState<Relationship[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [systemPrompt, setSystemPrompt] = useState<string>(FALLBACK_SYSTEM_PROMPT);
  const [userPromptTemplate, setUserPromptTemplate] = useState<string>(FALLBACK_USER_TEMPLATE);

  useEffect(() => {
    fetchPromptDefaults()
      .then((d) => {
        setSystemPrompt(d.system_prompt);
        setUserPromptTemplate(d.user_prompt_template);
      })
      .catch(() => { /* use fallbacks */ });
  }, []);

  const normalizeId = (name: string) => name.replace(/\s+/g, '_').toLowerCase();

  const processGraphResults = useCallback((
    { entities: rawEntities, relationships: rawRelationships }: { entities: RawEntity[], relationships: RawRelationship[] }
  ) => {
    const entityMap = new Map<string, Entity>();
    rawEntities.forEach(rawEntity => {
      const id = normalizeId(rawEntity.name);
      if (!entityMap.has(id)) {
        entityMap.set(id, { ...rawEntity, id });
      }
    });
    const updatedEntities = Array.from(entityMap.values());

    const relationshipMap = new Map<string, Relationship>();
    rawRelationships.forEach(rawRel => {
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
    const updatedRelationships = Array.from(relationshipMap.values());

    setEntities(updatedEntities);
    setRelationships(updatedRelationships);
  }, []);

  const handleAnalyze = useCallback(async () => {
    if (inputMode === 'url' && (!url.trim() || !/^(http|https)s?:\/\//.test(url))) {
      setError('Please enter a valid URL (e.g., https://...).');
      return;
    }
    if (inputMode === 'text' && !text.trim()) {
      setError('Please enter text to analyze.');
      return;
    }
    setIsLoading(true);
    setError(null);
    setEntities([]);
    setRelationships([]);

    try {
      const response = await analyzeWithBackend({
        model_type: 'openrouter',
        input_mode: inputMode,
        ...(inputMode === 'url' ? { url: url.trim() } : { text: text.trim() }),
        system_prompt: systemPrompt.trim() || null,
        user_prompt_template: userPromptTemplate.trim() || null,
      });
      if (response.extracted_text) setText(response.extracted_text);
      processGraphResults(response.data);
    } catch (e: any) {
      console.error(e);
      setError(e.message || 'An unexpected error occurred. Please try again.');
    } finally {
      setIsLoading(false);
    }
  }, [url, text, inputMode, systemPrompt, userPromptTemplate, processGraphResults]);

  const clearAll = () => {
    setUrl('');
    setText('');
    setEntities([]);
    setRelationships([]);
    setError(null);
    setIsLoading(false);
  };

  const handleDownloadEntities = () => {
    const csvData = entities.map(e => ({ 'entityId:ID': e.id, 'name': e.name, ':LABEL': e.label }));
    downloadCsv(csvData, 'entities.csv');
  };

  const handleDownloadRelationships = () => {
    const csvData = relationships.map(r => ({ ':START_ID': r.source, ':END_ID': r.target, ':TYPE': r.type }));
    downloadCsv(csvData, 'relationships.csv');
  };

  const isAnalyzeDisabled = isLoading;
  const hasResults = entities.length > 0 || relationships.length > 0;

  return (
    <div className="min-h-screen bg-[#020617] text-slate-100 font-sans flex flex-col">
      <header className="bg-[#0f172a]/80 backdrop-blur-sm border-b border-white/5 sticky top-0 z-10">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <h1 className="text-2xl font-bold bg-gradient-to-br from-white to-slate-400 bg-clip-text text-transparent">Graph Extractor</h1>
            <nav className="flex gap-1">
              <button
                onClick={() => setActiveTab('analyze')}
                className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all ${activeTab === 'analyze' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-900/30' : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'}`}
              >
                Analyze
              </button>
              <button
                onClick={() => setActiveTab('about')}
                className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all flex items-center gap-1.5 ${activeTab === 'about' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-900/30' : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'}`}
              >
                <Icon name="information-circle" className="w-5 h-5" />
                About
              </button>
            </nav>
          </div>
        </div>
      </header>

      <main className="flex-grow container mx-auto p-4 sm:p-6 lg:p-8">
        <div className="max-w-4xl mx-auto">
          {activeTab === 'about' ? (
            <div className="p-4 sm:p-6 rounded-xl bg-white/[0.02] border border-white/5 space-y-6">
              <h2 className="text-xl font-bold text-slate-100">About Graph Extractor</h2>
              <p className="text-slate-400 text-sm leading-relaxed">
                This tool extracts <strong className="text-slate-200">entities</strong> (people, organisations, locations, concepts) and <strong className="text-slate-200">relationships</strong> between them from text or a webpage URL.
                The backend uses the OpenRouter API key from <code className="bg-slate-800 px-1 rounded text-indigo-300">.env</code>; it fetches the page (if URL), sends the content plus your prompts to the LLM, parses the JSON response, and returns entities and relationships. You can export CSV for use in knowledge graphs (e.g. Neo4j).
              </p>

              <div>
                <h3 className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-3">System flow</h3>
                <div className="rounded-xl bg-slate-900 border border-white/10 p-4 overflow-x-auto" aria-hidden="true">
                  <svg viewBox="0 0 540 80" className="w-full min-h-[72px] text-slate-400" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <defs>
                      <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                        <path d="M0 0 L8 4 L0 8 Z" fill="currentColor" />
                      </marker>
                    </defs>
                    <rect x="8" y="18" width="88" height="44" rx="6" className="fill-slate-800 stroke-slate-500" />
                    <text x="52" y="45" className="fill-slate-300 text-[11px] font-medium" textAnchor="middle">URL or text</text>
                    <path d="M96 40 L124 40" markerEnd="url(#arrow)" className="stroke-slate-500" />
                    <rect x="124" y="18" width="88" height="44" rx="6" className="fill-slate-800 stroke-slate-500" />
                    <text x="168" y="42" className="fill-slate-300 text-[11px] font-medium" textAnchor="middle">Backend</text>
                    <text x="168" y="55" className="fill-slate-500 text-[9px]" textAnchor="middle">fetch + prompt</text>
                    <path d="M212 40 L240 40" markerEnd="url(#arrow)" className="stroke-slate-500" />
                    <rect x="240" y="18" width="88" height="44" rx="6" className="fill-slate-800 stroke-slate-500" />
                    <text x="284" y="42" className="fill-slate-300 text-[11px] font-medium" textAnchor="middle">OpenRouter</text>
                    <text x="284" y="55" className="fill-slate-500 text-[9px]" textAnchor="middle">LLM → JSON</text>
                    <path d="M328 40 L356 40" markerEnd="url(#arrow)" className="stroke-slate-500" />
                    <rect x="356" y="18" width="88" height="44" rx="6" className="fill-slate-800 stroke-slate-500" />
                    <text x="400" y="42" className="fill-slate-300 text-[11px] font-medium" textAnchor="middle">Parse</text>
                    <text x="400" y="55" className="fill-slate-500 text-[9px]" textAnchor="middle">entities & rels</text>
                    <path d="M444 40 L472 40" markerEnd="url(#arrow)" className="stroke-slate-500" />
                    <rect x="472" y="18" width="56" height="44" rx="6" className="fill-slate-800 stroke-indigo-500/50" />
                    <text x="500" y="45" className="fill-slate-300 text-[10px] font-medium" textAnchor="middle">Table</text>
                    <text x="500" y="58" className="fill-slate-500 text-[9px]" textAnchor="middle">/ CSV</text>
                  </svg>
                </div>
              </div>

              <p className="text-slate-400 text-sm leading-relaxed">
                You can make the extraction more specific by editing the prompts below. Use <code className="bg-slate-800 px-1 rounded text-indigo-300">__TEXT_TO_ANALYZE__</code> in the user prompt where the content should be inserted.
              </p>
              <div>
                <label htmlFor="system-prompt" className="block text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-1">System tone (role / style)</label>
                <textarea
                  id="system-prompt"
                  value={systemPrompt}
                  onChange={(e) => setSystemPrompt(e.target.value)}
                  rows={3}
                  className="w-full px-4 py-3 bg-slate-900 border border-white/10 rounded-xl text-slate-200 text-sm font-mono resize-y focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 placeholder-slate-500"
                  placeholder="e.g. You are a helpful assistant..."
                />
              </div>
              <div>
                <label htmlFor="user-prompt" className="block text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-1">User prompt (instructions). Use __TEXT_TO_ANALYZE__ where content goes.</label>
                <textarea
                  id="user-prompt"
                  value={userPromptTemplate}
                  onChange={(e) => setUserPromptTemplate(e.target.value)}
                  rows={18}
                  className="w-full px-4 py-3 bg-slate-900 border border-white/10 rounded-xl text-slate-200 text-sm font-mono resize-y focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 placeholder-slate-500"
                  placeholder="Instructions and JSON schema..."
                />
              </div>
            </div>
          ) : (
            <>
          <div className="p-4 sm:p-6 rounded-xl bg-slate-900 border border-white/10">
            <div className="flex border-b border-white/10 mb-4 gap-2">
              <button
                onClick={() => setInputMode('url')}
                className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all ${inputMode === 'url' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-900/30' : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'}`}
              >
                Analyze from URL
              </button>
              <button
                onClick={() => setInputMode('text')}
                className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all ${inputMode === 'text' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-900/30' : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'}`}
              >
                Analyze from Text
              </button>
            </div>

            {inputMode === 'url' ? (
              <div>
                <label htmlFor="url-input" className="block text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-1">Website URL</label>
                <input
                  id="url-input"
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://example.com/article"
                  className="w-full px-4 py-3 bg-slate-900 border border-white/10 rounded-xl text-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 placeholder-slate-500"
                />
              </div>
            ) : (
              <div>
                <label htmlFor="text-input" className="block text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-1">Text Content</label>
                <textarea
                  id="text-input"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Paste your text here..."
                  className="w-full h-48 px-4 py-3 bg-slate-900 border border-white/10 rounded-xl text-slate-200 text-sm font-mono resize-y focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 placeholder-slate-500"
                  aria-label="Text Content Input"
                />
              </div>
            )}

            <div className="mt-4 flex flex-col sm:flex-row items-center gap-4">
              <button
                onClick={handleAnalyze}
                disabled={isAnalyzeDisabled}
                className="w-full sm:w-auto flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 px-4 py-2.5 rounded-xl text-white text-sm font-semibold shadow-lg shadow-indigo-900/30 transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none"
              >
                {isLoading ? <Spinner /> : (inputMode === 'url' ? <Icon name="link" className="w-5 h-5"/> : <Icon name="document-text" className="w-5 h-5"/>)}
                {isLoading ? 'Analyzing...' : (inputMode === 'url' ? 'Fetch & Analyze' : 'Extract Relationships')}
              </button>
              <button
                  onClick={clearAll}
                  className="w-full sm:w-auto flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-all text-sm font-semibold"
                >
                  <Icon name="x-circle" className="w-5 h-5" />
                  Clear All
              </button>
            </div>
          </div>

          {error && (
            <div className="mt-6 p-4 rounded-xl bg-white/[0.02] border border-white/10" role="alert">
              <p className="font-bold text-red-400">Error</p>
              <p className="text-sm text-slate-400 mt-1">{error}</p>
            </div>
          )}

          {hasResults && (
            <div className="mt-8 space-y-8">
              <div>
                <div className="flex justify-between items-center mb-2">
                  <h2 className="text-xl font-bold text-slate-100">Entities</h2>
                  <button
                    onClick={handleDownloadEntities}
                    className="inline-flex items-center gap-2 px-4 py-2.5 bg-slate-800 border border-white/10 rounded-xl text-slate-200 hover:bg-slate-700 hover:border-orange-500/30 transition-all text-sm font-medium"
                  >
                    <Icon name="download" className="w-3.5 h-3.5 text-orange-400" />
                    Download CSV
                  </button>
                </div>
                <div className="rounded-xl bg-white/[0.02] border border-white/5 overflow-hidden">
                  <DataTable
                    headers={['ID', 'Name', 'Label']}
                    data={entities.map(e => [e.id, e.name, e.label])}
                  />
                </div>
              </div>

              <div>
                <div className="flex justify-between items-center mb-2">
                  <h2 className="text-xl font-bold text-slate-100">Relationships</h2>
                  <button
                    onClick={handleDownloadRelationships}
                    className="inline-flex items-center gap-2 px-4 py-2.5 bg-slate-800 border border-white/10 rounded-xl text-slate-200 hover:bg-slate-700 hover:border-orange-500/30 transition-all text-sm font-medium"
                  >
                    <Icon name="download" className="w-3.5 h-3.5 text-orange-400" />
                    Download CSV
                  </button>
                </div>
                <div className="rounded-xl bg-white/[0.02] border border-white/5 overflow-hidden">
                  <DataTable
                    headers={['Source', 'Target', 'Type']}
                    data={relationships.map(r => [r.source, r.target, r.type])}
                  />
                </div>
              </div>
            </div>
          )}
            </>
          )}
        </div>
      </main>
    </div>
  );
};

export default App;
