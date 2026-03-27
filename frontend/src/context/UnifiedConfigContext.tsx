/**
 * Unified config for FIND Tools — single source of truth for all module settings.
 * Persists to localStorage under rag_config_* keys.
 */
import React, { createContext, useContext, useState, useCallback } from 'react';

const STORAGE_PREFIX = 'rag_config_';

// --- Shared LLM (OpenRouter / OpenAI) — Chat backend + Entity Extractor browser calls ---
export interface LlmConfig {
  provider: 'openrouter' | 'openai';
  openRouterApiKey: string;
  openaiApiKey: string;
}

// --- Chat ---
export interface ChatConfig {
  /** Prepended to the RAG system prompt so teams can state role and research standards */
  researcherProfile: string;
  customPrompt: string;
  selectedModelId: string;
  /** research = use selected model; draft = use server OPENROUTER_FAST_MODEL (fast/cheap) */
  passMode: 'research' | 'draft';
}

/** Default role / standards block — prepended to the RAG template below */
export const DEFAULT_RESEARCHER_PROFILE = `You are a senior research analyst conducting document-grounded investigations.
Stay impartial, cite evidence, and clearly flag uncertainty or gaps in the sources.`;

const DEFAULT_CHAT_PROMPT = `INSTRUCTIONS:
1. Answer ONLY using the information in the provided context
2. If the answer is not in the context, respond: "The information is not found in the provided documents."
3. Cite your sources using [1], [2], etc. referring to the context numbers
4. Be concise but thorough
5. Use markdown formatting for clarity

CONTEXT:
{context}

Answer the following question based ONLY on the context above.`;

// --- Entity Extractor only (not RAG Chat — separate key rag_config_entity_extractor; not mixed with chat.*) ---
/** Built-in default for Entity Extractor system_prompt; Chat researcherProfile/customPrompt are unchanged */
export const DEFAULT_ENTITY_EXTRACTOR_SYSTEM_PROMPT = `Act as a high-precision OSINT data parser. Your sole task is to extract entities (Persons, Organisations, Locations, Digital Aliases, Financial Identifiers and associated relationships between entities) from the provided text into a structured format.

Output Requirements:

Respond exclusively with a single, minified JSON object.

Do not use Markdown formatting, backticks, or preamble.

If an entity type is not found, return an empty array for that key.

Ensure all strings are properly escaped for JSON compliance.

Schema Template:
{"entities":{"persons":[],"organisations":[],"locations":[],"digital_footprint":[]},"relationships":{"links":[{"source":"","target":"","type":"","description":""}]}}`;

export interface EntityExtractorConfig {
  neo4jUri: string;
  neo4jUsername: string;
  neo4jPassword: string;
  autoPushNeo4j: boolean;
  /**
   * Entity Extractor only — sent as system_prompt to /api/analyse. Does not affect Chat Settings.
   * Empty falls back to OOCP /api/prompt-defaults at run time in EntityExtractor.tsx.
   */
  systemPromptTemplate: string;
}

// --- Companies House ---
export interface CompaniesHouseConfig {
  apiKey: string;
}

// --- Name screening (OpenSanctions / Aleph / Sayari) — stored in browser, sent per request ---
export interface ScreeningConfig {
  openSanctionsApiKey: string;
  alephApiKey: string;
  /** Empty = use server default (aleph.occrp.org) */
  alephApiBase: string;
  sayariClientId: string;
  sayariClientSecret: string;
  /** Empty = use server default (api.sayari.com) */
  sayariApiBase: string;
}

// --- Full config ---
export interface UnifiedConfig {
  llm: LlmConfig;
  chat: ChatConfig;
  entityExtractor: EntityExtractorConfig;
  companiesHouse: CompaniesHouseConfig;
  screening: ScreeningConfig;
}

const defaultConfig: UnifiedConfig = {
  llm: {
    provider: 'openrouter',
    openRouterApiKey: '',
    openaiApiKey: '',
  },
  chat: {
    researcherProfile: DEFAULT_RESEARCHER_PROFILE,
    customPrompt: DEFAULT_CHAT_PROMPT,
    selectedModelId: '',
    passMode: 'research',
  },
  entityExtractor: {
    neo4jUri: '',
    neo4jUsername: 'neo4j',
    neo4jPassword: '',
    autoPushNeo4j: false,
    systemPromptTemplate: DEFAULT_ENTITY_EXTRACTOR_SYSTEM_PROMPT,
  },
  companiesHouse: {
    apiKey: '',
  },
  screening: {
    openSanctionsApiKey: '',
    alephApiKey: '',
    alephApiBase: '',
    sayariClientId: '',
    sayariClientSecret: '',
    sayariApiBase: '',
  },
};

function loadFromStorage(): UnifiedConfig {
  const result = JSON.parse(JSON.stringify(defaultConfig));
  try {
    const llmRaw = localStorage.getItem(`${STORAGE_PREFIX}llm`);
    if (llmRaw) {
      const parsed = JSON.parse(llmRaw);
      result.llm = { ...result.llm, ...parsed };
    }
    const raw = localStorage.getItem(`${STORAGE_PREFIX}chat`);
    if (raw) {
      const parsed = JSON.parse(raw);
      result.chat = { ...result.chat, ...parsed };
    }
    const ee = localStorage.getItem(`${STORAGE_PREFIX}entity_extractor`);
    if (ee) {
      const parsed = JSON.parse(ee) as Record<string, unknown>;
      // Legacy: model lived on entity extractor — merge into shared chat model id once
      const legacyModel = parsed.selectedModel;
      let migratedModel = false;
      if (typeof legacyModel === 'string' && legacyModel && !result.chat.selectedModelId) {
        result.chat.selectedModelId = legacyModel;
        migratedModel = true;
      }
      delete parsed.selectedModel;
      result.entityExtractor = { ...result.entityExtractor, ...parsed } as EntityExtractorConfig;
      try {
        if (migratedModel) {
          localStorage.setItem(`${STORAGE_PREFIX}chat`, JSON.stringify(result.chat));
        }
        localStorage.setItem(`${STORAGE_PREFIX}entity_extractor`, JSON.stringify(result.entityExtractor));
      } catch {}
    }
    const ch = localStorage.getItem(`${STORAGE_PREFIX}companies_house`);
    if (ch) {
      const parsed = JSON.parse(ch);
      result.companiesHouse = { ...result.companiesHouse, ...parsed };
    }
    const scr = localStorage.getItem(`${STORAGE_PREFIX}screening`);
    if (scr) {
      const parsed = JSON.parse(scr);
      result.screening = { ...result.screening, ...parsed };
    }
    // EE-only: old saves with empty template get the OSINT default (Chat prompts untouched — separate key)
    if (!result.entityExtractor.systemPromptTemplate?.trim()) {
      result.entityExtractor.systemPromptTemplate = DEFAULT_ENTITY_EXTRACTOR_SYSTEM_PROMPT;
    }
  } catch {}
  return result;
}

const STORAGE_KEY_MAP: Record<keyof UnifiedConfig, string> = {
  llm: 'llm',
  chat: 'chat',
  entityExtractor: 'entity_extractor',
  companiesHouse: 'companies_house',
  screening: 'screening',
};

function saveToStorage(key: keyof UnifiedConfig, value: UnifiedConfig[typeof key]) {
  try {
    localStorage.setItem(`${STORAGE_PREFIX}${STORAGE_KEY_MAP[key]}`, JSON.stringify(value));
  } catch {}
}

// Migrate legacy keys to unified config on first load
function migrateLegacyKeys(config: UnifiedConfig): UnifiedConfig {
  try {
    const ragPrompt = localStorage.getItem('rag_custom_prompt');
    if (ragPrompt) {
      config.chat.customPrompt = ragPrompt;
      localStorage.removeItem('rag_custom_prompt');
    }
    const eeProvider = localStorage.getItem('ee_provider');
    if (eeProvider === 'openrouter' || eeProvider === 'openai') {
      config.llm.provider = eeProvider;
    }
    const keys = ['ee_openrouter_api_key', 'ee_openai_api_key', 'ee_neo4j_uri', 'ee_neo4j_username', 'ee_neo4j_password', 'ee_auto_push_neo4j'];
    const map: Record<string, keyof EntityExtractorConfig> = {
      ee_neo4j_uri: 'neo4jUri',
      ee_neo4j_username: 'neo4jUsername',
      ee_neo4j_password: 'neo4jPassword',
      ee_auto_push_neo4j: 'autoPushNeo4j',
    };
    keys.forEach((k) => {
      const v = localStorage.getItem(k);
      if (v !== null) {
        const target = map[k];
        if (k === 'ee_openrouter_api_key') {
          config.llm.openRouterApiKey = v;
        } else if (k === 'ee_openai_api_key') {
          config.llm.openaiApiKey = v;
        } else if (target) {
          (config.entityExtractor as unknown as Record<string, unknown>)[target] =
            target === 'autoPushNeo4j' ? v === 'true' : v;
        }
        localStorage.removeItem(k);
      }
    });
    // Legacy: provider/keys lived on entity_extractor JSON — fold into llm once
    const eeLegacy = config.entityExtractor as unknown as { provider?: string; openRouterApiKey?: string; openaiApiKey?: string };
    if (eeLegacy.provider && (eeLegacy.provider === 'openrouter' || eeLegacy.provider === 'openai')) {
      config.llm.provider = eeLegacy.provider;
    }
    if (eeLegacy.openRouterApiKey) config.llm.openRouterApiKey = eeLegacy.openRouterApiKey;
    if (eeLegacy.openaiApiKey) config.llm.openaiApiKey = eeLegacy.openaiApiKey;
    delete eeLegacy.provider;
    delete eeLegacy.openRouterApiKey;
    delete eeLegacy.openaiApiKey;
  } catch {}
  return config;
}

interface ConfigContextValue {
  config: UnifiedConfig;
  setLlmConfig: (updates: Partial<LlmConfig>) => void;
  setChatConfig: (updates: Partial<ChatConfig>) => void;
  setEntityExtractorConfig: (updates: Partial<EntityExtractorConfig>) => void;
  setCompaniesHouseConfig: (updates: Partial<CompaniesHouseConfig>) => void;
  setScreeningConfig: (updates: Partial<ScreeningConfig>) => void;
}

const ConfigContext = createContext<ConfigContextValue | null>(null);

export function UnifiedConfigProvider({ children }: { children: React.ReactNode }) {
  const [config, setConfig] = useState<UnifiedConfig>(() => {
    const loaded = loadFromStorage();
    return migrateLegacyKeys(loaded);
  });

  const setLlmConfig = useCallback((updates: Partial<LlmConfig>) => {
    setConfig((prev) => {
      const next = { ...prev.llm, ...updates };
      saveToStorage('llm', next);
      return { ...prev, llm: next };
    });
  }, []);

  const setChatConfig = useCallback((updates: Partial<ChatConfig>) => {
    setConfig((prev) => {
      const next = { ...prev.chat, ...updates };
      saveToStorage('chat', next);
      return { ...prev, chat: next };
    });
  }, []);

  const setEntityExtractorConfig = useCallback((updates: Partial<EntityExtractorConfig>) => {
    setConfig((prev) => {
      const next = { ...prev.entityExtractor, ...updates };
      saveToStorage('entityExtractor', next);
      return { ...prev, entityExtractor: next };
    });
  }, []);

  const setCompaniesHouseConfig = useCallback((updates: Partial<CompaniesHouseConfig>) => {
    setConfig((prev) => {
      const next = { ...prev.companiesHouse, ...updates };
      saveToStorage('companiesHouse', next);
      return { ...prev, companiesHouse: next };
    });
  }, []);

  const setScreeningConfig = useCallback((updates: Partial<ScreeningConfig>) => {
    setConfig((prev) => {
      const next = { ...prev.screening, ...updates };
      saveToStorage('screening', next);
      return { ...prev, screening: next };
    });
  }, []);

  return (
    <ConfigContext.Provider
      value={{
        config,
        setLlmConfig,
        setChatConfig,
        setEntityExtractorConfig,
        setCompaniesHouseConfig,
        setScreeningConfig,
      }}
    >
      {children}
    </ConfigContext.Provider>
  );
}

export function useUnifiedConfig() {
  const ctx = useContext(ConfigContext);
  if (!ctx) throw new Error('useUnifiedConfig must be used within UnifiedConfigProvider');
  return ctx;
}
