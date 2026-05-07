import { describe, it, expect, beforeEach, vi } from 'vitest';

import { apiGet } from './api-client';

describe('api-client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.history.pushState({}, '', '/');
  });

  it('unwraps the FastAPI envelope on 2xx', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: { count: 3 }, meta: { layer: 'graph' } }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const [data, meta] = await apiGet<{ count: number }>('/api/graph/health');
    expect(data).toEqual({ count: 3 });
    expect(meta?.layer).toBe('graph');
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('throws ApiError with category on 4xx', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error: { category: 'validation', message: 'bad uid', retryable: false },
        }),
        { status: 400, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiGet('/api/graph/context/bogus')).rejects.toMatchObject({
      name: 'ApiError',
      status: 400,
      category: 'validation',
    });
  });

  it('rewrites /api paths under /p/<slug>/ to per-project endpoints', async () => {
    window.history.pushState({}, '', '/p/myproj/board');
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ data: {}, meta: {} }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await apiGet('/api/board/list');
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain('/api/p/myproj/board/list');
  });
});
