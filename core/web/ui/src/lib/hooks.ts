import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { apiGet } from './api-client';

/**
 * Shared React-Query hook wrapping api-client.
 *
 * PURPOSE: Any page can call this directly; caching is shared via the
 *          QueryClient in main.tsx.
 * NOTES:   Hub-scope awareness — the queryKey includes the active
 *          project slug parsed from window.location.pathname so
 *          navigating between /p/A/... and /p/B/... never serves A's
 *          cached payload for B.  Without this, the api-client rewrite
 *          correctly hits /api/p/<slug>/... per request but React Query
 *          reuses the identical [path, ...key] cache entry across
 *          projects — every board/graph/search/cognition view would
 *          render the FIRST project's data for every other one until
 *          the cache expires.  See HubHome / ProjectSwitcher for the
 *          navigation path that triggered the bug.
 */
function currentProjectSlug(): string | null {
  if (typeof window === 'undefined') return null;
  const m = /^\/p\/([^/]+)(?:\/|$)/.exec(window.location.pathname);
  return m ? decodeURIComponent(m[1]) : null;
}

export function useApiGet<T>(
  key: readonly unknown[],
  path: string,
  params?: Record<string, unknown>,
  options?: { enabled?: boolean },
): UseQueryResult<T, Error> {
  // Hub-scoped endpoints (/api/hub/*) are global and MUST NOT be
  // partitioned by slug — otherwise the project switcher re-fetches
  // the same list every navigation.  Everything else partitions.
  const isHubGlobal = path.startsWith('/api/hub/');
  const scope = isHubGlobal ? '__global__' : (currentProjectSlug() ?? '__cwd__');
  return useQuery<T, Error>({
    queryKey: ['cos-scope', scope, path, params, ...key],
    queryFn: async () => {
      const [data] = await apiGet<T>(path, params);
      return data;
    },
    enabled: options?.enabled ?? true,
  });
}

/**
 * Invalidation that matches the scoped queryKey shape.
 *
 * PURPOSE: Without this helper, SSE bump++ + old-style
 *          `qc.invalidateQueries({ queryKey: ['/api/board/list'] })`
 *          no-ops silently because real keys are
 *          `['cos-scope', slug, '/api/board/list', ...]` — that's why
 *          the board stopped auto-refreshing.
 */
export function invalidateApiQueries(
  qc: import('@tanstack/react-query').QueryClient,
  path: string,
): Promise<void> {
  return qc.invalidateQueries({
    predicate: (query) => {
      const k = query.queryKey as unknown[];
      return Array.isArray(k) && k.includes(path);
    },
  });
}
