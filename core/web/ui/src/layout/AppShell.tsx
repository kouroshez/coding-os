import type { ReactNode } from 'react';
import { useMemo } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { Brain, KanbanSquare, Network, Search, Settings } from 'lucide-react';
import Inspector from '@/layout/Inspector';
import ProjectSwitcher from '@/layout/ProjectSwitcher';

/**
 * Unified application shell.
 *
 * PURPOSE: Top-level chrome shared by every feature (board, graph,
 *          search, cognition, hub).  Renders the primary nav, the
 *          always-visible ProjectSwitcher, an optional Inspector aside,
 *          and an outlet for the current route.
 * INPUT:   brandingSlot (optional) — extra chrome after the switcher
 *          (e.g. a breadcrumb for stacked contexts).  Kept for
 *          backwards compatibility; most pages pass nothing.
 * OUTPUT:  Single-root layout that fills 100% height.
 * NOTES:   NavLinks are scope-aware: when the URL contains /p/<slug>/,
 *          every feature link preserves the slug so switching tabs
 *          doesn't silently drop you back into the unscoped cwd-default.
 */

const NAV = [
  { feature: 'board', label: 'Board', Icon: KanbanSquare, end: true },
  { feature: 'graph', label: 'Graph', Icon: Network, end: false },
  { feature: 'search', label: 'Search', Icon: Search, end: true },
  { feature: 'cognition', label: 'Cognition', Icon: Brain, end: false },
  { feature: 'settings', label: 'Settings', Icon: Settings, end: true },
] as const;

const PROJECT_SCOPE_RE = /^\/p\/([^/]+)(?:\/|$)/;

export default function AppShell({
  brandingSlot,
}: {
  brandingSlot?: ReactNode;
}) {
  const location = useLocation();
  const scopeSlug = useMemo(() => {
    const m = PROJECT_SCOPE_RE.exec(location.pathname);
    return m ? decodeURIComponent(m[1]) : null;
  }, [location.pathname]);

  const showInspector =
    /^\/graph/.test(location.pathname) ||
    /^\/search/.test(location.pathname) ||
    /^\/cognition/.test(location.pathname) ||
    /^\/p\/[^/]+\/(graph|search|cognition)/.test(location.pathname);

  const linkFor = (feature: string): string =>
    scopeSlug ? `/p/${encodeURIComponent(scopeSlug)}/${feature}` : `/${feature}`;

  return (
    <div className="flex h-full min-h-0 w-full flex-col bg-[var(--board)] text-[var(--ink)]">
      <header
        className="flex shrink-0 items-center gap-4 border-b-2 border-[var(--line)] px-4 py-2"
        style={{ background: 'var(--board)' }}
      >
        <div
          className="font-semibold tracking-wide text-[var(--accent)]"
          style={{ fontFamily: "'Permanent Marker', cursive", fontSize: 18 }}
        >
          Coding OS
        </div>
        <ProjectSwitcher />
        {brandingSlot && (
          <div className="flex items-center gap-2 text-xs text-[var(--ink-soft)]">
            {brandingSlot}
          </div>
        )}
        <nav className="flex flex-1 flex-wrap items-center gap-1" aria-label="Primary">
          {NAV.map(({ feature, label, Icon, end }) => (
            <NavLink
              key={feature}
              to={feature === 'settings' ? '/settings' : linkFor(feature)}
              end={end}
              className={({ isActive }) =>
                [
                  'flex items-center gap-2 rounded px-3 py-1.5 text-xs font-semibold',
                  'font-mono transition-colors',
                  isActive
                    ? 'bg-[var(--col-bg)] text-[var(--accent)] ring-1 ring-[var(--col-border)]'
                    : 'text-[var(--ink-soft)] hover:bg-[var(--col-bg)] hover:text-[var(--ink)]',
                ].join(' ')
              }
            >
              <Icon size={14} aria-hidden />
              {label}
            </NavLink>
          ))}
        </nav>
      </header>
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <div className="min-h-0 min-w-0 flex-1 overflow-hidden">
          <Outlet />
        </div>
        {showInspector && (
          <aside
            className="hidden w-[320px] shrink-0 overflow-auto border-l border-[var(--col-border)] bg-[var(--col-bg)] text-[var(--ink)] md:block"
            aria-label="Inspector"
          >
            <Inspector />
          </aside>
        )}
      </div>
    </div>
  );
}
