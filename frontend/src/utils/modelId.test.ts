import { describe, expect, it } from 'vitest';
import { normalizeModelIdForProvider } from './modelId';

describe('normalizeModelIdForProvider', () => {
  it('normalises openrouter-prefixed id for OpenAI provider', () => {
    expect(normalizeModelIdForProvider('openai/gpt-4o-mini', 'openai')).toBe('gpt-4o-mini');
  });

  it('keeps provider-prefixed id for OpenRouter provider', () => {
    expect(normalizeModelIdForProvider('openai/gpt-4o-mini', 'openrouter')).toBe('openai/gpt-4o-mini');
  });

  it('returns safe defaults when id is missing', () => {
    expect(normalizeModelIdForProvider('', 'openai')).toBe('gpt-4o-mini');
    expect(normalizeModelIdForProvider('', 'openrouter')).toBe('openai/gpt-4o-mini');
  });
});

