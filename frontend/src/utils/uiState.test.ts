import { describe, expect, it } from 'vitest';
import { DEFAULT_UI_STATE, loadUiState, saveUiState, UI_STATE_KEY } from './uiState';

describe('uiState persistence', () => {
  it('saves and reloads tab/session state for reload continuity', () => {
    const memory = new Map<string, string>();
    const storage = {
      getItem: (k: string) => memory.get(k) ?? null,
      setItem: (k: string, v: string) => {
        memory.set(k, v);
      },
    };

    const state = {
      activeTab: 'entity' as const,
      chatSubTab: 'history' as const,
      entitySubTab: 'settings' as const,
      chSubTab: 'pipeline' as const,
      selectedDocumentId: 'doc-123',
      conversationId: 'conv-456',
    };
    saveUiState(state, storage);
    const loaded = loadUiState(storage);
    expect(loaded).toEqual(state);
    expect(memory.has(UI_STATE_KEY)).toBe(true);
  });

  it('falls back safely when persisted state is malformed', () => {
    const storage = {
      getItem: () => '{bad-json',
      setItem: () => undefined,
    };
    expect(loadUiState(storage)).toEqual(DEFAULT_UI_STATE);
  });
});
