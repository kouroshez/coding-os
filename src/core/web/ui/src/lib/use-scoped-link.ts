import { useCallback, useMemo } from 'react';
import { useLocation } from 'react-router-dom';

const PROJECT_SCOPE_RE = /^\/p\/([^/]+)(?:\/|$)/;

/**
 * Features that live as tabs *inside* the Workspace shell. Their scoped route
 * is `/p/<slug>/workspace/<tab>`, not `/p/<slug>/<tab>` — the distinction the
 * project picker got wrong, sending `chat` and `memory` to a path matching no
 * route, which fell through the `*` catch-all back to Hub home.
 */
export const WORKSPACE_TABS = new Set(['overview', 'chat', 'board', 'search', 'memory', 'design']);

/**
 * The project-scoped URL for a feature. The only place that decides whether a
 * feature nests under /workspace, so the pickers and App.tsx cannot drift.
 */
export function projectFeaturePath(feature: string, slug: string): string {
  const clean = feature.replace(/^\/+/, '');
  const prefix = `/p/${encodeURIComponent(slug)}`;
  return WORKSPACE_TABS.has(clean) ? `${prefix}/workspace/${clean}` : `${prefix}/${clean}`;
}

/**
 * useScopedLink — single source of truth for "where does this nav link
 * point under the current project scope?".
 *
 * Background: the SPA has two URL shapes for every project-aware
 * feature — `/p/<slug>/board` when a project is selected, and `/board`
 * (which routes to NeedProjectPage) when not.  Many components used to
 * hardcode the un-scoped `/board` form, which made every Quick Action
 * / Panel / Inspector link "lose" the active project on click — the
 * SPA would bounce the user to the project picker even though one was
 * already selected.
 *
 * Returns:
 *   slug         — the active project slug parsed from the URL, or null.
 *   scopedLink   — (featurePath, suffix?) => string.  Prepends the slug
 *                  when present; otherwise returns the un-scoped path so
 *                  callers can keep their existing fallback behaviour.
 *   replaceScope — same shape, but builds an URL that swaps the slug
 *                  while preserving the rest of the path (Quick Switch).
 */
export function useScopedLink() {
  const location = useLocation();
  const slug = useMemo(() => {
    const m = PROJECT_SCOPE_RE.exec(location.pathname);
    return m ? decodeURIComponent(m[1]) : null;
  }, [location.pathname]);

  const scopedLink = useCallback(
    (featurePath: string, suffix = '') => {
      const clean = featurePath.replace(/^\/+/, '');
      const tail = suffix ? (suffix.startsWith('?') ? suffix : `/${suffix.replace(/^\/+/, '')}`) : '';
      if (slug) return `/p/${encodeURIComponent(slug)}/${clean}${tail}`;
      return `/${clean}${tail}`;
    },
    [slug],
  );

  return { slug, scopedLink };
}
