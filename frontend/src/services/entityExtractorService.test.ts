import { afterEach, describe, expect, it, vi } from 'vitest';
import { analyzeWithBackend, analyzeWithBackendStreaming } from './entityExtractorService';

const originalFetch = globalThis.fetch;

function mockResponse(body: unknown, init?: { status?: number; statusText?: string }) {
  return new Response(typeof body === 'string' ? body : JSON.stringify(body), {
    status: init?.status ?? 200,
    statusText: init?.statusText ?? 'OK',
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('entityExtractorService', () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('surfaces backend detail for non-stream analyze errors', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      mockResponse({ detail: 'Invalid model id' }, { status: 500, statusText: 'Internal Server Error' })
    ) as unknown as typeof fetch;

    await expect(
      analyzeWithBackend({ model_type: 'openai', input_mode: 'text', text: 'hello' })
    ).rejects.toThrow('Invalid model id');
  });

  it('surfaces backend detail for stream endpoint errors', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      mockResponse({ detail: 'Stream exploded' }, { status: 500, statusText: 'Internal Server Error' })
    ) as unknown as typeof fetch;

    await expect(
      analyzeWithBackendStreaming(
        { model_type: 'openrouter', input_mode: 'text', text: 'hello' },
        () => undefined
      )
    ).rejects.toThrow('Stream exploded');
  });

  it('falls back to non-stream endpoint when stream route is missing', async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(mockResponse({ detail: 'Not found' }, { status: 404, statusText: 'Not Found' }))
      .mockResolvedValueOnce(
        mockResponse({ success: true, data: { entities: [], relationships: [] }, extracted_text: 'ok' })
      ) as unknown as typeof fetch;

    const result = await analyzeWithBackendStreaming(
      { model_type: 'openai', input_mode: 'text', text: 'hello' },
      () => undefined
    );
    expect(result.success).toBe(true);
    expect(result.extracted_text).toBe('ok');
  });
});

