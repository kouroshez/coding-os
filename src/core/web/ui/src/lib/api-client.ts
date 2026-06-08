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

// Hub-aware path rewriter: when the SPA is mounted under /p/<slug>/...
// (Hub project-scoped routes), every /api/... request gets rewritten to
// /api/p/<slug>/... so the ProjectScopeMiddleware on the backend picks
// the right sqlite DB and project root for the request.  Non-/api/
// paths (e.g. /health) stay global and are never rewritten.
const PROJECT_SLUG_RE = /^\/p\/([^/]+)(?:\/|$)/;

const rewriteForProjectScope = (path: string): string => {
  if (!path.startsWith('/api/')) return path;
  if (path.startsWith('/api/p/')) return path;
  if (path.startsWith('/api/hub/')) return path;
  const match = PROJECT_SLUG_RE.exec(window.location.pathname);
  if (!match) return path;
  const slug = match[1];
  return `/api/p/${encodeURIComponent(slug)}/${path.slice('/api/'.length)}`;
};

const buildUrl = (path: string, params?: Record<string, unknown>): string => {
  const base = DEFAULT_BASE;
  const scopedPath = rewriteForProjectScope(path);
  const url = new URL(base + scopedPath, window.location.origin);
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

// CSRF double-submit: the hub's SecurityGateMiddleware issues a readable
// `cos_csrf` cookie; mutation requests must echo it in the X-CSRF-Token
// header. Same-origin only — in cross-origin dev the cookie isn't sent and
// the server's Origin allowlist vouches for the dev origin instead. See
// docs/engineering/hub-architecture.md#localhost-security-gate-originhost-allowlist--csrf
const readCsrfToken = (): string | null => {
  if (typeof document === 'undefined') return null;
  const match = /(?:^|;\s*)cos_csrf=([^;]+)/.exec(document.cookie);
  return match ? decodeURIComponent(match[1]) : null;
};

// Exported so raw-fetch SSE callers (chat start + follow-up turns) that can't
// use the JSON fetch wrapper still satisfy the double-submit CSRF gate.
export const csrfHeader = (): Record<string, string> => {
  const token = readCsrfToken();
  return token ? { 'X-CSRF-Token': token } : {};
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

/**
 * Resolve an API path to the final URL that will be hit by `fetch` /
 * `EventSource` — exposed for callers (SSE, <img>) that don't go
 * through the fetch wrapper but still need the per-project rewrite.
 */
export function resolveApiUrl(path: string, params?: Record<string, unknown>): string {
  return buildUrl(path, params);
}

// Reads (board list, task detail, task history) hit endpoints that do git +
// sqlite work; a slow or wedged server must surface an error state, never an
// infinite spinner. Apply a default abort timeout when the caller didn't pass
// its own signal, and translate abort/network failures into an ApiError the
// UI already knows how to render.
const DEFAULT_GET_TIMEOUT_MS = 20_000;

export async function apiGet<T>(
  path: string,
  params?: Record<string, unknown>,
  init?: RequestInit,
): Promise<[T, ApiMeta | null]> {
  const signal = init?.signal ?? AbortSignal.timeout(DEFAULT_GET_TIMEOUT_MS);
  try {
    const res = await fetch(buildUrl(path, params), {
      method: 'GET',
      headers: { Accept: 'application/json' },
      ...init,
      signal,
    });
    return handle<T>(res);
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && (err.name === 'TimeoutError' || err.name === 'AbortError')) {
      throw new ApiError(
        504,
        'unavailable',
        `request timed out after ${DEFAULT_GET_TIMEOUT_MS / 1000}s`,
        true,
      );
    }
    throw new ApiError(0, 'unavailable', err instanceof Error ? err.message : 'network error', true);
  }
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
      ...csrfHeader(),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    ...init,
  });
  return handle<T>(res);
}

export async function apiPatch<T>(
  path: string,
  body?: unknown,
  init?: RequestInit,
): Promise<[T, ApiMeta | null]> {
  const res = await fetch(buildUrl(path), {
    method: 'PATCH',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...csrfHeader(),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    ...init,
  });
  return handle<T>(res);
}

export async function apiDelete<T>(
  path: string,
  init?: RequestInit,
): Promise<[T, ApiMeta | null]> {
  const res = await fetch(buildUrl(path), {
    method: 'DELETE',
    headers: { Accept: 'application/json', ...csrfHeader() },
    ...init,
  });
  return handle<T>(res);
}

// Path-typed helpers — re-export the codegen `paths` interface so callers can
// derive request/response shapes from the OpenAPI spec without hand-writing
// types. Run `npm run gen-api` (with the hub up on :9188) to refresh.
//
// Usage:
//   import type { paths } from './api-types';
//   type CtxResp = paths['/api/graph/context/{uid_or_name}']['get']['responses']['200']['content']['application/json'];
//   const [data] = await apiGet<CtxResp>('/api/graph/context/...');
export type { paths, components, operations } from './api-types';
