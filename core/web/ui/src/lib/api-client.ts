// Typed fetch wrapper that unwraps the FastAPI envelope shape from S4:
//   { data, meta }   on 2xx
//   { error: {...} } on 4xx/5xx
//
// Usage:
//   const [graph, meta] = await apiGet<ExportPayload>('/api/graph/export', {...});
//   const [card] = await apiPost<Card>('/api/board/create', body);

const DEFAULT_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') || '';

export interface ApiMeta {
  layer?: string;
  query?: string;
  [key: string]: unknown;
}

export class ApiError extends Error {
  public readonly status: number;
  public readonly category: string;
  public readonly retryable: boolean;

  constructor(status: number, category: string, message: string, retryable = false) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.category = category;
    this.retryable = retryable;
  }
}

const buildUrl = (path: string, params?: Record<string, unknown>): string => {
  const base = DEFAULT_BASE;
  const url = new URL(base + path, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === null) continue;
      if (Array.isArray(v)) {
        url.searchParams.set(k, v.join(','));
      } else {
        url.searchParams.set(k, String(v));
      }
    }
  }
  return url.pathname + url.search;
};

const handle = async <T>(res: Response): Promise<[T, ApiMeta | null]> => {
  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      throw new ApiError(res.status, 'internal', 'non-JSON response from server');
    }
  }

  if (!res.ok) {
    const errObj =
      body && typeof body === 'object' && 'error' in body
        ? ((body as { error: Record<string, unknown> }).error ?? {})
        : {};
    const category = String(errObj['category'] ?? 'internal');
    const message = String(errObj['message'] ?? res.statusText ?? 'request failed');
    const retryable = Boolean(errObj['retryable']);
    throw new ApiError(res.status, category, message, retryable);
  }

  // /health returns a flat object, not wrapped — accept both shapes.
  if (body && typeof body === 'object' && 'data' in body) {
    const envelope = body as { data: T; meta?: ApiMeta };
    return [envelope.data, envelope.meta ?? null];
  }
  return [body as T, null];
};

export async function apiGet<T>(
  path: string,
  params?: Record<string, unknown>,
  init?: RequestInit,
): Promise<[T, ApiMeta | null]> {
  const res = await fetch(buildUrl(path, params), {
    method: 'GET',
    headers: { Accept: 'application/json' },
    ...init,
  });
  return handle<T>(res);
}

export async function apiPost<T>(
  path: string,
  body?: unknown,
  init?: RequestInit,
): Promise<[T, ApiMeta | null]> {
  const res = await fetch(buildUrl(path), {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    ...init,
  });
  return handle<T>(res);
}
