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

export interface UseApiGetOptions {
  enabled?: boolean;
  /** Polling interval in ms — translated to TanStack `refetchInterval`. */
  refetchIntervalMs?: number;
  /** How long a result stays fresh (ms) — translated to TanStack `staleTime`.
   *  Caches expensive probes (e.g. the gh-api git-state) so re-opening a tab
   *  doesn't re-round-trip. */
  staleTimeMs?: number;
  /**
   * Merge the envelope's sibling `meta` block into the returned object
   * (as `data.meta`) — apiGet returns `[data, meta]` and the default
   * path drops meta, which hid the graph export's budget provenance
   * from the truncation badge (TASK-402). Object payloads only.
   */
  includeMeta?: boolean;
}

export function useApiGet<T>(
  key: readonly unknown[],
  path: string,
  params?: Record<string, unknown>,
  options?: UseApiGetOptions,
): UseQueryResult<T, Error> {
  // Hub-scoped endpoints (/api/hub/*) are global and MUST NOT be
  // partitioned by slug — otherwise the project switcher re-fetches
  // the same list every navigation.  Everything else partitions.
  const isHubGlobal = path.startsWith('/api/hub/');
  const scope = isHubGlobal ? '__global__' : (currentProjectSlug() ?? '__cwd__');
  return useQuery<T, Error>({
    queryKey: ['cos-scope', scope, path, params, ...key],
    queryFn: async () => {
      const [data, meta] = await apiGet<T>(path, params);
      if (options?.includeMeta && data && typeof data === 'object' && !Array.isArray(data)) {
        return { ...(data as object), meta } as T;
      }
      return data;
    },
    enabled: options?.enabled ?? true,
    refetchInterval: options?.refetchIntervalMs,
    staleTime: options?.staleTimeMs,
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
