/**
 * FIND Tools RAG UI (see `branding.ts`)
 *
 * Main tabs: Chat | Entity Extractor | Companies House | Name screening | Tools | About
 * Chat/EE/CH have sub-tabs: [Main] | History | Settings
 */

import { useState, useEffect, useCallback, useMemo, lazy, Suspense } from 'react';
import {
  BookOpen,
  PanelLeft,
  Quote,
  MessageSquare,
  GitBranch,
  Building2,
  Info,
  ChevronDown,
  Network,
  Wrench,
  Zap,
  Fingerprint,
} from 'lucide-react';
import { DocumentLibrary } from './components/DocumentLibrary';
import { ChatInterface } from './components/ChatInterface';
import { CitationPanel } from './components/CitationPanel';
import { MemoryPanel } from './components/MemoryPanel';
import { ChatSettings } from './components/ChatSettings';
import { EntityExtractorSettings } from './components/EntityExtractorSettings';
import { CompaniesHouseSettings } from './components/CompaniesHouseSettings';
import { CompaniesHouseHistory } from './components/CompaniesHouseHistory';
import { SubTabBar } from './components/SubTabBar';
import { useToast } from './components/ToastContext';
import { useUnifiedConfig } from './context/UnifiedConfigContext';
import { DocumentSummary, Citation, RetrievedChunk, AvailableModel, RetrievalTrace, WorkspaceSummary, GlobalSearchHit } from './types';
import { listDocuments, getHealth, getAvailableModels, listWorkspaces, createWorkspace } from './services/api';
import { useMediaQuery } from './hooks/useMediaQuery';
import {
  loadUiState,
  saveUiState,
  type MainTab,
  type ChatSubTab,
  type EntitySubTab,
  type CHSubTab,
  type PersistedUiState,
} from './utils/uiState';
import { PRODUCT_TITLE, PRODUCT_TAGLINE } from './branding';

const About = lazy(() => import('./components/About').then((m) => ({ default: m.About })));
const EntityExtractor = lazy(() =>
  import('./components/EntityExtractor').then((m) => ({ default: m.EntityExtractor }))
);
const CompaniesHousePipeline = lazy(() =>
  import('./components/CompaniesHousePipeline').then((m) => ({ default: m.CompaniesHousePipeline }))
);
const ToolsPage = lazy(() => import('./components/ToolsPage').then((m) => ({ default: m.ToolsPage })));
const NameScreening = lazy(() =>
  import('./components/NameScreening').then((m) => ({ default: m.NameScreening }))
);

function App() {
  const { toast } = useToast();
  const { config, setChatConfig } = useUnifiedConfig();
  const initialUiState = useMemo(() => loadUiState(), []);

  // State
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [selectedDocument, setSelectedDocument] = useState<DocumentSummary | null>(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(
    initialUiState.selectedDocumentId
  );
  const [conversationId, setConversationId] = useState<string | null>(initialUiState.conversationId);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isCitationPanelOpen, setIsCitationPanelOpen] = useState(
    () => typeof window !== 'undefined' && window.innerWidth >= 1024
  );
  const [currentCitations, setCurrentCitations] = useState<Citation[]>([]);
  const [currentChunks, setCurrentChunks] = useState<RetrievedChunk[]>([]);
  const [currentRetrievalTrace, setCurrentRetrievalTrace] = useState<RetrievalTrace | null>(null);
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [workspaceFilterId, setWorkspaceFilterId] = useState<string | null>(null);
  const [uploadWorkspaceId, setUploadWorkspaceId] = useState<string | null>(null);
  const isLg = useMediaQuery('(min-width: 1024px)');
  const [apiReachable, setApiReachable] = useState<boolean | null>(null);
  const [activeTab, setActiveTab] = useState<MainTab>(initialUiState.activeTab);
  const [chatSubTab, setChatSubTab] = useState<ChatSubTab>(initialUiState.chatSubTab);
  const [entitySubTab, setEntitySubTab] = useState<EntitySubTab>(initialUiState.entitySubTab);
  const [chSubTab, setCHSubTab] = useState<CHSubTab>(initialUiState.chSubTab);
  const [loadedMessages, setLoadedMessages] = useState<import('./types').Message[] | null>(null);
  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([]);
  const [fastModelId, setFastModelId] = useState<string>('');
  const [showModelMenu, setShowModelMenu] = useState(false);

  // Cloud-first: hide vLLM in the UI even if the API lists it (local dev)
  const cloudModels = useMemo(
    () => availableModels.filter((m) => m.provider !== 'vllm'),
    [availableModels]
  );

  // Sync selectedModel from config with API models on load
  const rawSelected = config.chat.selectedModelId || cloudModels[0]?.id || '';
  const selectedIsHiddenVllm =
    !!config.chat.selectedModelId &&
    availableModels.some((m) => m.id === config.chat.selectedModelId && m.provider === 'vllm');
  const effectiveModelId = selectedIsHiddenVllm ? cloudModels[0]?.id || '' : rawSelected;

  /** Actual OpenRouter model id sent to the API (draft = server fast model) */
  const modelIdForChat = useMemo(() => {
    if (config.chat.passMode === 'draft' && fastModelId) return fastModelId;
    return effectiveModelId;
  }, [config.chat.passMode, fastModelId, effectiveModelId]);

  // Banner copy: local dev uses Vite /api proxy; production build may set VITE_API_BASE_URL
  const apiTargetHint = useMemo(() => {
    const v = import.meta.env.VITE_API_BASE_URL;
    return v ? String(v).replace(/\/$/, '') : '/api → localhost:8000';
  }, []);

  // Check API on mount; while down, poll so the banner clears when you start the backend
  useEffect(() => {
    getHealth()
      .then(() => setApiReachable(true))
      .catch(() => setApiReachable(false));
  }, []);

  useEffect(() => {
    if (apiReachable !== false) return;
    const id = setInterval(() => {
      getHealth()
        .then(() => setApiReachable(true))
        .catch(() => setApiReachable(false));
    }, 8000);
    return () => clearInterval(id);
  }, [apiReachable]);

  // Load available models on mount
  useEffect(() => {
    getAvailableModels()
      .then((response) => {
        setAvailableModels(response.models);
        if (response.fast_model) setFastModelId(response.fast_model);
        const visible = response.models.filter((m) => m.provider !== 'vllm');
        const defaultModel = visible.find((m) => m.id === response.default_model) ?? visible[0];
        const fallback = defaultModel?.id ?? visible[0]?.id ?? '';
        if (!config.chat.selectedModelId && fallback) {
          setChatConfig({ selectedModelId: fallback });
        }
      })
      .catch((err) => console.error('Failed to load models:', err));
  }, []);

  // Persist switch away from hidden vLLM selection
  useEffect(() => {
    if (selectedIsHiddenVllm && cloudModels[0]?.id) {
      setChatConfig({ selectedModelId: cloudModels[0].id });
    }
  }, [selectedIsHiddenVllm, cloudModels, setChatConfig]);

  const loadDocuments = useCallback(async () => {
    try {
      const docs = await listDocuments(workspaceFilterId);
      setDocuments(docs);
    } catch (err) {
      console.error('Failed to load documents:', err);
    }
  }, [workspaceFilterId]);

  const loadWorkspaces = useCallback(async () => {
    try {
      const ws = await listWorkspaces();
      setWorkspaces(ws);
      setUploadWorkspaceId((prev) => (prev == null && ws[0]?.id ? ws[0].id : prev));
    } catch (e) {
      console.error('Failed to load workspaces:', e);
    }
  }, []);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  useEffect(() => {
    if (!selectedDocumentId) return;
    const doc = documents.find((d) => d.id === selectedDocumentId) ?? null;
    if (doc && (!selectedDocument || selectedDocument.id !== doc.id)) {
      setSelectedDocument(doc);
    }
  }, [documents, selectedDocumentId, selectedDocument]);

  useEffect(() => {
    const state: PersistedUiState = {
      activeTab,
      chatSubTab,
      entitySubTab,
      chSubTab,
      selectedDocumentId,
      conversationId,
    };
    saveUiState(state);
  }, [activeTab, chatSubTab, entitySubTab, chSubTab, selectedDocumentId, conversationId]);

  useEffect(() => {
    loadWorkspaces();
  }, [loadWorkspaces]);

  // Toggle sources panel — ` (backtick) when not typing in an input
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== '`' || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement;
      if (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable) return;
      e.preventDefault();
      setIsCitationPanelOpen((v) => !v);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const handleSelectDocument = (doc: DocumentSummary | null) => {
    setSelectedDocument(doc);
    setSelectedDocumentId(doc?.id ?? null);
    setConversationId(null);
    setLoadedMessages(null);
    setIsCitationPanelOpen(false);
  };

  const handleSelectConversation = (conversationId: string, messages: import('./types').Message[]) => {
    setConversationId(conversationId);
    setLoadedMessages(messages);
    setActiveTab('chat');
    setChatSubTab('chat');
  };

  const handleShowCitations = (
    citations: Citation[],
    chunks: RetrievedChunk[],
    retrievalTrace?: RetrievalTrace | null
  ) => {
    setCurrentCitations(citations);
    setCurrentChunks(chunks);
    setCurrentRetrievalTrace(retrievalTrace ?? null);
    setIsCitationPanelOpen(true);
  };

  const handleFocusDocument = (documentId: string) => {
    const doc = documents.find((d) => d.id === documentId);
    if (doc) {
      setSelectedDocument(doc);
      setSelectedDocumentId(doc.id);
      setActiveTab('chat');
      setChatSubTab('chat');
    }
  };

  const handleGlobalSearchSelect = async (hit: GlobalSearchHit) => {
    let doc = documents.find((d) => d.id === hit.document_id);
    if (!doc) {
      const docs = await listDocuments(workspaceFilterId);
      setDocuments(docs);
      doc = docs.find((d) => d.id === hit.document_id);
    }
    if (doc) {
      setSelectedDocument(doc);
      setSelectedDocumentId(doc.id);
      setActiveTab('chat');
      setChatSubTab('chat');
    }
  };

  const handleCreateWorkspace = async (name: string) => {
    const w = await createWorkspace(name);
    setWorkspaces((prev) => [...prev, w]);
    setUploadWorkspaceId(w.id);
    setWorkspaceFilterId(w.id);
  };

  const handleConversationCreated = (id: string) => {
    setConversationId(id);
  };

  const modelsByProvider = useMemo(
    () =>
      cloudModels.reduce((acc, model) => {
        const provider = model.provider || 'unknown';
        if (!acc[provider]) acc[provider] = [];
        acc[provider].push(model);
        return acc;
      }, {} as Record<string, AvailableModel[]>),
    [cloudModels]
  );

  const providerLabels: Record<string, string> = {
    openrouter: 'OpenRouter',
    openai: 'OpenAI',
    unknown: 'Other',
  };

  // Prefer full list so draft fast model resolves even if not in cloud-only slice
  const selectedModelData = useMemo(
    () => availableModels.find((m) => m.id === modelIdForChat),
    [availableModels, modelIdForChat]
  );

  const mainTabs = [
    { id: 'chat' as const, label: 'Chat', icon: <MessageSquare className="w-4 h-4" /> },
    { id: 'entity' as const, label: 'Entity Extractor', icon: <GitBranch className="w-4 h-4" /> },
    { id: 'ch' as const, label: 'Companies House', icon: <Building2 className="w-4 h-4" /> },
    { id: 'screening' as const, label: 'Name screening', icon: <Fingerprint className="w-4 h-4" /> },
    { id: 'tools' as const, label: 'Tools', icon: <Wrench className="w-4 h-4" /> },
    { id: 'about' as const, label: 'About', icon: <Info className="w-4 h-4" /> },
  ];

  const handleToolsSelectTab = useCallback((tabId: string) => {
    if (tabId === 'chat' || tabId === 'memory') {
      setActiveTab('chat');
      setChatSubTab(tabId === 'memory' ? 'history' : 'chat');
    } else if (tabId === 'entity-extractor') {
      setActiveTab('entity');
      setEntitySubTab('extract');
    } else if (tabId === 'about') {
      setActiveTab('about');
    }
  }, []);

  const tabFallback = (
    <div className="h-full flex items-center justify-center text-sm text-ink-muted">Loading...</div>
  );

  return (
    <div className="flex h-screen bg-surface text-ink overflow-hidden">
      {/* Sidebar */}
      <aside
        className={`
          bg-surface-muted backdrop-blur-xl border-r border-slate-200 transition-all duration-300
          ${isSidebarOpen ? 'w-80' : 'w-0 overflow-hidden'}
        `}
      >
        <div className="h-full flex flex-col">
          <div className="p-4 border-b border-slate-200">
            <div className="flex items-center gap-2">
              <div className="bg-accent p-2 rounded-xl shadow-sm">
                <BookOpen className="w-5 h-5 text-white" />
              </div>
              <h1 className="text-lg font-bold text-ink leading-tight">
                {PRODUCT_TITLE}
              </h1>
            </div>
            <p className="text-xs text-ink-muted mt-1">{PRODUCT_TAGLINE}</p>
            {apiReachable === false && (
              <p className="text-xs text-amber-700 mt-2 leading-snug">
                API unreachable — expected base <span className="font-mono">{apiTargetHint}</span>.
                {!import.meta.env.VITE_API_BASE_URL && (
                  <>
                    {' '}
                    From <span className="font-mono">FIND Tools</span> run{' '}
                    <span className="font-mono">docker compose up -d</span> or{' '}
                    <span className="font-mono">./scripts/run_backend_venv.sh</span>.
                  </>
                )}{' '}
                Clears when <span className="font-mono">GET /health</span> succeeds (retry every 8s).
              </p>
            )}
          </div>
          <div className="flex-1 p-4 overflow-hidden">
            <DocumentLibrary
              documents={documents}
              selectedDocument={selectedDocument}
              onSelectDocument={handleSelectDocument}
              onDocumentsChange={loadDocuments}
              onError={(msg) => toast(msg, 'error')}
              workspaces={workspaces}
              workspaceFilterId={workspaceFilterId}
              uploadWorkspaceId={uploadWorkspaceId}
              onWorkspaceFilterChange={setWorkspaceFilterId}
              onUploadWorkspaceChange={setUploadWorkspaceId}
              onCreateWorkspace={handleCreateWorkspace}
              onGlobalSearchSelect={handleGlobalSearchSelect}
            />
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 flex flex-col min-w-0">
        <header className="h-14 bg-surface-card border-b border-slate-200 flex items-center justify-between px-4">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className="p-2 text-ink-muted hover:text-ink hover:bg-slate-100 rounded-lg transition-colors"
            >
              <PanelLeft className="w-5 h-5" />
            </button>

            {/* Main tabs */}
            <div className="flex items-center gap-1 border-r border-slate-200 pr-3 mr-3">
              {mainTabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`
                    flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all
                    ${activeTab === tab.id
                      ? 'bg-accent text-white shadow-sm'
                      : 'text-ink-muted hover:text-ink hover:bg-slate-100'
                    }
                  `}
                >
                  {tab.icon}
                  {tab.label}
                </button>
              ))}
            </div>

            {activeTab === 'chat' && selectedDocument && (
              <div>
                <h2 className="text-sm font-medium text-ink">{selectedDocument.original_name}</h2>
                <p className="text-xs text-ink-muted">
                  {selectedDocument.total_pages} pages • {selectedDocument.chunk_count} chunks
                </p>
              </div>
            )}
            {activeTab === 'chat' && !selectedDocument && <h2 className="text-sm font-medium text-ink">All Documents</h2>}
          </div>

          <div className="flex items-center gap-3">
            {/* Research vs fast draft — Chat tab only */}
            {activeTab === 'chat' && (
              <div
                className="flex items-center rounded-xl border border-slate-200 bg-surface-muted p-0.5 text-xs font-medium"
                title="Research uses your selected model; Draft uses the server fast model (cheaper, quicker)."
              >
                <button
                  type="button"
                  onClick={() => setChatConfig({ passMode: 'research' })}
                  className={`px-2.5 py-1 rounded-lg transition-colors ${
                    config.chat.passMode !== 'draft' ? 'bg-white text-ink shadow-sm' : 'text-ink-muted hover:text-ink'
                  }`}
                >
                  Research
                </button>
                <button
                  type="button"
                  onClick={() => setChatConfig({ passMode: 'draft' })}
                  className={`flex items-center gap-1 px-2.5 py-1 rounded-lg transition-colors ${
                    config.chat.passMode === 'draft' ? 'bg-white text-ink shadow-sm' : 'text-ink-muted hover:text-ink'
                  }`}
                >
                  <Zap className="w-3.5 h-3.5" />
                  Draft
                </button>
              </div>
            )}
            {/* Model selector — shared by Chat + Entity Extractor (+ About); only place to pick model */}
            {(activeTab === 'chat' || activeTab === 'entity' || activeTab === 'about') &&
              cloudModels.length > 0 && (
              <div className="relative z-50">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setShowModelMenu(!showModelMenu);
                  }}
                  className="flex items-center gap-2 px-3 py-1.5 bg-surface-muted border border-slate-200 rounded-xl hover:bg-slate-200 transition-all text-sm"
                >
                  {(selectedModelData || modelIdForChat) && (
                    <>
                      <div className="p-1 rounded bg-amber-100 text-amber-700">
                        <Network className="w-3.5 h-3.5" />
                      </div>
                      <span className="text-ink font-medium">
                        {selectedModelData?.name ?? modelIdForChat.split('/').pop() ?? modelIdForChat}
                      </span>
                    </>
                  )}
                  <ChevronDown className={`w-4 h-4 text-ink-muted transition-transform ${showModelMenu ? 'rotate-180' : ''}`} />
                </button>

                {showModelMenu && (
                  <>
                    <div className="fixed inset-0 z-[40]" onClick={() => setShowModelMenu(false)} />
                    <div
                      className="absolute top-full right-0 mt-2 w-64 bg-surface-card border border-slate-200 rounded-2xl shadow-lg z-[50] overflow-hidden py-2"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {Object.entries(modelsByProvider).map(([provider, models]) => (
                        <div key={provider}>
                          <div className="px-4 py-2 text-xs font-bold text-ink-muted uppercase tracking-widest">
                            {providerLabels[provider] || provider}
                          </div>
                          {models.map((model) => (
                            <button
                              key={model.id}
                              onClick={(e) => {
                                e.stopPropagation();
                                setChatConfig({ selectedModelId: model.id, passMode: 'research' });
                                setShowModelMenu(false);
                              }}
                              className={`w-full flex items-start gap-3 px-4 py-3 hover:bg-slate-50 transition-all text-left ${
                                effectiveModelId === model.id ? 'bg-accent-light' : ''
                              }`}
                            >
                              <div className="p-1.5 rounded mt-0.5 bg-amber-100 text-amber-700">
                                <Network className="w-3.5 h-3.5" />
                              </div>
                              <div>
                                <p className="text-xs font-bold text-ink">{model.name}</p>
                              </div>
                            </button>
                          ))}
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}

            {activeTab === 'chat' && chatSubTab === 'chat' && (
              <button
                onClick={() => setIsCitationPanelOpen(!isCitationPanelOpen)}
                className={`
                  flex items-center gap-2 px-3 py-1.5 rounded-xl text-sm transition-all
                  ${isCitationPanelOpen ? 'bg-accent text-white shadow-sm' : 'text-ink-muted hover:text-ink hover:bg-slate-100'}
                `}
              >
                <Quote className="w-4 h-4" />
                Sources
              </button>
            )}
          </div>
        </header>

        {/* Content area */}
        <div className="flex-1 overflow-hidden flex flex-col">
          <div className={activeTab === 'screening' ? 'h-full' : 'hidden'}>
            <Suspense fallback={tabFallback}>
              <NameScreening />
            </Suspense>
          </div>
          <div className={activeTab === 'tools' ? 'h-full' : 'hidden'}>
            <Suspense fallback={tabFallback}>
              <ToolsPage onSelectTab={handleToolsSelectTab} />
            </Suspense>
          </div>
          <div className={activeTab === 'about' ? 'h-full' : 'hidden'}>
            <Suspense fallback={tabFallback}>
              <About />
            </Suspense>
          </div>
          <div className={activeTab === 'chat' ? 'h-full flex flex-col' : 'hidden'}>
            <>
              <div className="px-6 pt-4">
                <SubTabBar
                  tabs={[
                    { id: 'chat', label: 'Chat' },
                    { id: 'history', label: 'History' },
                    { id: 'settings', label: 'Settings' },
                  ]}
                  activeId={chatSubTab}
                  onSelect={(id) => setChatSubTab(id as ChatSubTab)}
                  accentColor="green"
                />
              </div>
              <div className="flex-1 overflow-hidden flex flex-col lg:flex-row min-h-0">
                <div className={chatSubTab === 'chat' ? 'flex flex-1 min-h-0 min-w-0' : 'hidden'}>
                  <div className="flex-1 min-w-0 min-h-0 overflow-hidden flex flex-col">
                    <ChatInterface
                      selectedDocument={selectedDocument}
                      conversationId={conversationId}
                      loadedMessages={loadedMessages}
                      onConversationCreated={handleConversationCreated}
                      onShowCitations={handleShowCitations}
                      selectedModel={modelIdForChat}
                      researcherProfile={config.chat.researcherProfile}
                      customPrompt={config.chat.customPrompt}
                    />
                  </div>
                  {isLg && isCitationPanelOpen && (
                    <CitationPanel
                      isOpen
                      onClose={() => setIsCitationPanelOpen(false)}
                      citations={currentCitations}
                      chunks={currentChunks}
                      retrievalTrace={currentRetrievalTrace}
                      layout="rail"
                      onFocusDocument={handleFocusDocument}
                    />
                  )}
                </div>
                <div className={chatSubTab === 'history' ? 'flex-1 min-h-0' : 'hidden'}>
                  <MemoryPanel
                    documents={documents}
                    selectedDocument={selectedDocument}
                    onSelectConversation={handleSelectConversation}
                  />
                </div>
                <div className={chatSubTab === 'settings' ? 'flex-1 min-h-0' : 'hidden'}>
                  <ChatSettings fastModelId={fastModelId} />
                </div>
              </div>
            </>
          </div>
          <div className={activeTab === 'entity' ? 'h-full flex flex-col' : 'hidden'}>
            <>
              <div className="px-6 pt-4">
                <SubTabBar
                  tabs={[
                    { id: 'extract', label: 'Entity Extractor' },
                    { id: 'history', label: 'History' },
                    { id: 'settings', label: 'Settings' },
                  ]}
                  activeId={entitySubTab}
                  onSelect={(id) => setEntitySubTab(id as EntitySubTab)}
                  accentColor="green"
                />
              </div>
              <div className="flex-1 overflow-hidden">
                <div className={entitySubTab === 'extract' ? 'h-full' : 'hidden'}>
                  <Suspense fallback={tabFallback}>
                    <EntityExtractor />
                  </Suspense>
                </div>
                <div className={entitySubTab === 'history' ? 'h-full overflow-y-auto p-6 sm:p-10 custom-scrollbar flex items-center justify-center text-ink-muted' : 'hidden'}>
                    <div className="h-full overflow-y-auto p-6 sm:p-10 custom-scrollbar flex items-center justify-center text-ink-muted">
                    Extraction history is not persisted. Past extractions appear in the Entity Extractor tab during your session.
                  </div>
                </div>
                <div className={entitySubTab === 'settings' ? 'h-full' : 'hidden'}>
                  <EntityExtractorSettings />
                </div>
              </div>
            </>
          </div>
          <div className={activeTab === 'ch' ? 'h-full flex flex-col' : 'hidden'}>
            <>
              <div className="px-6 pt-4">
                <SubTabBar
                  tabs={[
                    { id: 'pipeline', label: 'Companies House' },
                    { id: 'history', label: 'History' },
                    { id: 'settings', label: 'Settings' },
                  ]}
                  activeId={chSubTab}
                  onSelect={(id) => setCHSubTab(id as CHSubTab)}
                  accentColor="green"
                />
              </div>
              <div className="flex-1 overflow-hidden">
                <div className={chSubTab === 'pipeline' ? 'h-full' : 'hidden'}>
                  <Suspense fallback={tabFallback}>
                    <CompaniesHousePipeline apiKey={config.companiesHouse.apiKey} />
                  </Suspense>
                </div>
                <div className={chSubTab === 'history' ? 'h-full' : 'hidden'}>
                  <CompaniesHouseHistory />
                </div>
                <div className={chSubTab === 'settings' ? 'h-full' : 'hidden'}>
                  <CompaniesHouseSettings />
                </div>
              </div>
            </>
          </div>
        </div>
      </main>

      {!isLg && (
        <CitationPanel
          isOpen={isCitationPanelOpen}
          onClose={() => setIsCitationPanelOpen(false)}
          citations={currentCitations}
          chunks={currentChunks}
          retrievalTrace={currentRetrievalTrace}
          layout="overlay"
          onFocusDocument={handleFocusDocument}
        />
      )}
    </div>
  );
}

export default App;
