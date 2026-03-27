import { describe, expect, it } from 'vitest';
import { clearDraftValue, loadDraftValue, saveDraftValue } from './draftState';

describe('draftState helpers', () => {
  it('saves then loads a value', () => {
    const key = 'draft-test-key';
    const memory = new Map<string, string>();
    const storage = {
      getItem: (k: string) => memory.get(k) ?? null,
      setItem: (k: string, v: string) => memory.set(k, v),
      removeItem: (k: string) => memory.delete(k),
    };
    saveDraftValue(key, 'hello', storage);
    expect(loadDraftValue(key, '', storage)).toBe('hello');
    clearDraftValue(key, storage);
    expect(loadDraftValue(key, '', storage)).toBe('');
  });

  it('returns fallback when missing', () => {
    const storage = {
      getItem: () => null,
      setItem: () => undefined,
      removeItem: () => undefined,
    };
    expect(loadDraftValue('missing-key', 'fallback', storage)).toBe('fallback');
  });
});
