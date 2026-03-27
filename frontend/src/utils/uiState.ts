export type MainTab = 'chat' | 'entity' | 'ch' | 'tools' | 'screening' | 'about';

const MAIN_TABS: readonly MainTab[] = ['chat', 'entity', 'ch', 'tools', 'screening', 'about'];

function isMainTab(value: string | undefined): value is MainTab {
  return !!value && (MAIN_TABS as readonly string[]).includes(value);
}
export type ChatSubTab = 'chat' | 'history' | 'settings';
export type EntitySubTab = 'extract' | 'history' | 'settings';
export type CHSubTab = 'pipeline' | 'history' | 'settings';

export type PersistedUiState = {
  activeTab: MainTab;
  chatSubTab: ChatSubTab;
  entitySubTab: EntitySubTab;
  chSubTab: CHSubTab;
  selectedDocumentId: string | null;
  conversationId: string | null;
};

export const UI_STATE_KEY = 'rag_v2_ui_state';

export const DEFAULT_UI_STATE: PersistedUiState = {
  activeTab: 'chat',
  chatSubTab: 'chat',
  entitySubTab: 'extract',
  chSubTab: 'pipeline',
  selectedDocumentId: null,
  conversationId: null,
};

export function loadUiState(
  storage: Pick<Storage, 'getItem'> | undefined = typeof window !== 'undefined'
    ? window.localStorage
    : undefined
): PersistedUiState {
  if (!storage) return DEFAULT_UI_STATE;
  try {
    const raw = storage.getItem(UI_STATE_KEY);
    if (!raw) return DEFAULT_UI_STATE;
    const parsed = JSON.parse(raw) as Partial<PersistedUiState>;
    return {
      activeTab: isMainTab(parsed.activeTab) ? parsed.activeTab : DEFAULT_UI_STATE.activeTab,
      chatSubTab: parsed.chatSubTab ?? DEFAULT_UI_STATE.chatSubTab,
      entitySubTab: parsed.entitySubTab ?? DEFAULT_UI_STATE.entitySubTab,
      chSubTab: parsed.chSubTab ?? DEFAULT_UI_STATE.chSubTab,
      selectedDocumentId: parsed.selectedDocumentId ?? null,
      conversationId: parsed.conversationId ?? null,
    };
  } catch {
    return DEFAULT_UI_STATE;
  }
}

export function saveUiState(
  state: PersistedUiState,
  storage: Pick<Storage, 'setItem'> | undefined = typeof window !== 'undefined'
    ? window.localStorage
    : undefined
): void {
  if (!storage) return;
  storage.setItem(UI_STATE_KEY, JSON.stringify(state));
}
