import { Navigate, useLocation, useParams } from 'react-router-dom';

/**
 * Where legacy flat routes go. Lives outside App.tsx so it can be tested
 * without importing the whole route tree (which pulls Sigma, and therefore
 * WebGL, into jsdom).
 *
 * Both helpers carry the query string and any trailing `:sessionId` across the
 * hop. A redirect that drops them turns a shared deep link into a bare tab —
 * the same "landed somewhere generic" failure as the picker bug they fix.
 */
export function RedirectToWorkspace({ sub }: { sub: string }) {
  const { slug, sessionId } = useParams<{ slug?: string; sessionId?: string }>();
  const { search } = useLocation();
  const base = slug ? `/p/${encodeURIComponent(slug)}/workspace/${sub}` : `/workspace/${sub}`;
  const tail = sessionId ? `/${encodeURIComponent(sessionId)}` : '';
  return <Navigate to={`${base}${tail}${search}`} replace />;
}

export function RedirectToDiagnostics({ sub }: { sub: string }) {
  const { slug } = useParams<{ slug?: string }>();
  const { search } = useLocation();
  const base = slug ? `/p/${encodeURIComponent(slug)}/diagnostics/${sub}` : `/diagnostics/${sub}`;
  return <Navigate to={`${base}${search}`} replace />;
}

// Settings merged into Config — old settings deep-links land on the
// Config tab; the global scope has no config surface, so it falls back to `/`.
export function RedirectToConfigSettings() {
  const { slug } = useParams<{ slug?: string }>();
  return <Navigate to={slug ? `/p/${encodeURIComponent(slug)}/config?tab=settings` : '/config'} replace />;
}
