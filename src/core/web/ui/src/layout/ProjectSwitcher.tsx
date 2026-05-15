/**
 * ProjectSwitcher — global chrome in AppShell that shows the current
 * project and lets you jump to any other registered project without
 * going back to the Hub home.
 *
 * PURPOSE: Close the "panel is single-project" gap — once you deep-link
 *          into /p/<slug>/board, every feature nav (Graph, Search,
 *          Cognition) stays inside that scope.  This component exposes
 *          the *other* direction: switch to a different slug on the
 *          same feature tab.
 *
 * BEHAVIOUR:
 *   - Renders the active project slug (or "Hub" when on /).
 *   - Click → dropdown of every project from /api/hub/projects.
 *   - Clicking a project navigates to the same feature under its slug
 *     (e.g. at /p/foo/graph, clicking "bar" → /p/bar/graph).
 *   - Dropdown also exposes a "← All projects" shortcut back to /.
 *
 * INPUT:    Reads pathname from react-router; fetches project list
 *           via useApiGet.
 * OUTPUT:   A button with a menu; no side effects beyond navigation.
 * NOTES:    Closes on outside click, Escape, or after navigate().
 *           Keyboard-accessible: aria-haspopup/-expanded + Enter/Space
 *           on the trigger.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useApiGet } from '@/lib/hooks';

interface HubProject {
  slug: string;
  path: string;
  created_at?: string;
  source?: string;
}

interface HubProjectsPayload {
  projects: HubProject[];
  count: number;
}

const PROJECT_SCOPE_RE = /^\/p\/([^/]+)(\/.*)?$/;
const FEATURE_PATH_RE = /^\/(dashboard|board|graph|search|cognition|observability|roles)(\/.*)?$/;

function parseCurrentScope(pathname: string): {
  slug: string | null;
  feature: string;
  rest: string;
} {
  const scoped = PROJECT_SCOPE_RE.exec(pathname);
  if (scoped) {
    const remainder = scoped[2] ?? '';
    const featMatch = FEATURE_PATH_RE.exec(remainder);
    return {
      slug: scoped[1],
      feature: featMatch?.[1] ?? 'board',
      rest: featMatch?.[2] ?? '',
    };
  }
  const featTop = FEATURE_PATH_RE.exec(pathname);
  if (featTop) {
    return { slug: null, feature: featTop[1], rest: featTop[2] ?? '' };
  }
  return { slug: null, feature: 'board', rest: '' };
}

function pathForSlug(slug: string | null, feature: string, rest: string): string {
  const tail = `/${feature}${rest}`;
  return slug ? `/p/${encodeURIComponent(slug)}${tail}` : tail;
}

export default function ProjectSwitcher() {
  const location = useLocation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const { slug: activeSlug, feature, rest } = useMemo(
    () => parseCurrentScope(location.pathname),
    [location.pathname],
  );

  const { data, isLoading } = useApiGet<HubProjectsPayload>(
    ['project-switcher'],
    '/api/hub/projects',
  );

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        !menuRef.current?.contains(target) &&
        !buttonRef.current?.contains(target)
      ) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const jumpTo = useCallback(
    (slug: string | null) => {
      navigate(pathForSlug(slug, feature, rest));
      setOpen(false);
    },
    [navigate, feature, rest],
  );

  const activeProject = data?.projects.find((p) => p.slug === activeSlug);
  const label = activeProject?.slug ?? (activeSlug ?? 'Hub home');

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-1.5 rounded-md border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2.5 py-1 font-mono text-[11px] text-[var(--cos-text)] transition-colors hover:border-[var(--cos-accent)] hover:text-[var(--cos-accent)]"
        title={
          activeProject
            ? `${activeProject.slug} — ${activeProject.path}`
            : 'switch project'
        }
      >
        <span
          aria-hidden
          className="inline-block h-1.5 w-1.5 rounded-full"
          style={{
            background: activeSlug ? 'var(--cos-accent)' : 'var(--cos-faint)',
          }}
        />
        <span className="max-w-[160px] truncate">{label}</span>
        <span aria-hidden style={{ opacity: 0.6 }}>
          ▾
        </span>
      </button>
      {open && (
        <div
          ref={menuRef}
          role="menu"
          aria-label="Switch project"
          className="absolute left-0 top-[calc(100%+4px)] z-50 w-[320px] overflow-hidden rounded-md border border-[var(--cos-border)] bg-[var(--cos-panel)] shadow-lg"
        >
          <div className="border-b border-[var(--cos-border)] px-3 py-2 text-[10px] uppercase tracking-wider text-[var(--cos-faint)]">
            projects {data?.count != null ? `· ${data.count}` : ''}
          </div>

          <button
            type="button"
            role="menuitem"
            onClick={() => {
              navigate('/');
              setOpen(false);
            }}
            className="flex w-full items-center justify-between px-3 py-2 text-left text-xs hover:bg-[var(--cos-grain)]"
          >
            <span className="font-semibold text-[var(--cos-accent)]">← All projects (Hub home)</span>
          </button>

          <div className="max-h-[320px] overflow-auto cos-scroll">
            {isLoading && (
              <div className="px-3 py-4 text-center text-xs text-[var(--cos-faint)]">
                loading…
              </div>
            )}
            {!isLoading && !data?.projects.length && (
              <div className="px-3 py-4 text-center text-xs text-[var(--cos-faint)]">
                no projects yet — register one on the Hub home
              </div>
            )}
            {!isLoading &&
              data?.projects.map((p) => {
                const isActive = p.slug === activeSlug;
                return (
                  <button
                    key={p.slug}
                    type="button"
                    role="menuitem"
                    onClick={() => jumpTo(p.slug)}
                    className={[
                      'flex w-full flex-col gap-0.5 border-t border-[var(--cos-border)] px-3 py-2 text-left text-xs transition-colors',
                      isActive
                        ? 'bg-[var(--cos-grain)] text-[var(--cos-accent)]'
                        : 'hover:bg-[var(--cos-grain)] text-[var(--cos-text)]',
                    ].join(' ')}
                  >
                    <span className="flex items-center gap-2 font-semibold">
                      {isActive && (
                        <span
                          aria-hidden
                          className="inline-block h-1.5 w-1.5 rounded-full"
                          style={{ background: 'var(--cos-accent)' }}
                        />
                      )}
                      {p.slug}
                    </span>
                    <span className="break-all font-mono text-[10px] text-[var(--cos-faint)]">
                      {p.path}
                    </span>
                  </button>
                );
              })}
          </div>
        </div>
      )}
    </div>
  );
}
