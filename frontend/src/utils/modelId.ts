/**
 * Model id normalisation helpers shared by Chat/Entity Extractor paths.
 */

export type LlmProvider = 'openrouter' | 'openai';

/**
 * Resolve a provider-compatible model id from a shared selected id.
 * - OpenAI expects plain model ids (e.g. "gpt-4o-mini")
 * - OpenRouter accepts provider-prefixed ids (e.g. "openai/gpt-4o-mini")
 */
export function normalizeModelIdForProvider(
  selectedModelId: string | null | undefined,
  provider: LlmProvider
): string {
  const selected = (selectedModelId ?? '').trim();
  if (provider === 'openai') {
    if (!selected) return 'gpt-4o-mini';
    return selected.includes('/') ? selected.split('/').pop() || 'gpt-4o-mini' : selected;
  }
  return selected || 'openai/gpt-4o-mini';
}

