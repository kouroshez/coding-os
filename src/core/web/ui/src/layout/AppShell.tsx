import type { ReactNode } from 'react';
import { useMemo } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { Brain, HeartPulse, LayoutDashboard, Network, SlidersHorizontal } from 'lucide-react';
import HealthAlarmBar from '@/layout/HealthAlarmBar';
import Inspector from '@/layout/Inspector';
import LiveStatus from '@/layout/LiveStatus';
import ProjectSwitcher from '@/layout/ProjectSwitcher';
import logoUrl from '@/assets/logo.png';
import ThemeToggle from '@/layout/ThemeToggle';

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
  { feature: 'workspace', label: 'Workspace', Icon: LayoutDashboard, end: false },
  { feature: 'graph', label: 'Graph', Icon: Network, end: false },
  { feature: 'cognition', label: 'Cognition', Icon: Brain, end: false },
  { feature: 'config', label: 'Config', Icon: SlidersHorizontal, end: false },
  { feature: 'diagnostics', label: 'Diagnostics', Icon: HeartPulse, end: false },
] as const;

/**
 * Features that ALWAYS link to the global /<feature> URL regardless
 * of current project scope.  Only Settings qualifies today — its
 * data is hub-wide (paths, budget caps, trace rotation) and has no
 * per-project meaning.
 *
 * Doctor / Sessions / Observability all expose hub-wide data BUT
 * their URLs follow project scope (linkFor) so users keep their
 * project context across nav.  Both /<feature> and /p/:slug/<feature>
 * routes render the same components.
 */
const HUB_LEVEL_FEATURES = new Set(['settings']);

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

  // Inspector is bound to the graph-store (`selectedNodeUid`) — it is
  // only meaningful on /graph. Other pages render their own context
  // panes (Cognition right-aside, Search inline expand) so the global
  // aside would just sit empty and steal width.
  const showInspector =
    /^\/graph(?:\/|$)/.test(location.pathname) ||
    /^\/p\/[^/]+\/graph(?:\/|$)/.test(location.pathname);

  const linkFor = (feature: string): string =>
    scopeSlug ? `/p/${encodeURIComponent(scopeSlug)}/${feature}` : `/${feature}`;

  return (
    <div className="flex h-full min-h-0 w-full flex-col bg-[var(--cos-bg)] text-[var(--cos-text)]">
      <header className="flex shrink-0 items-center gap-4 border-b border-[var(--cos-border)] bg-[var(--cos-panel)] px-4 py-2">
        <div className="flex shrink-0 items-center gap-2">
          <img src={logoUrl} alt="" aria-hidden="true" className="h-6 w-6 shrink-0" />
          <span className="text-[15px] font-bold tracking-tight text-[var(--cos-text)]">Coding OS</span>
        </div>
        <ProjectSwitcher />
        <LiveStatus />
        <HealthAlarmBar />
        {brandingSlot && (
          <div className="flex items-center gap-2 text-xs text-[var(--cos-muted)]">
            {brandingSlot}
          </div>
        )}
        <nav className="flex flex-1 flex-wrap items-center gap-1" aria-label="Primary">
          {NAV.map(({ feature, label, Icon, end }) => (
            <NavLink
              key={feature}
              to={HUB_LEVEL_FEATURES.has(feature) ? `/${feature}` : linkFor(feature)}
              end={end}
              className={({ isActive }) =>
                [
                  'flex items-center gap-2 rounded px-3 py-1.5 text-xs font-semibold',
                  'font-mono transition-colors',
                  isActive
                    ? 'bg-[var(--cos-grain)] text-[var(--cos-accent)] ring-1 ring-[var(--cos-border)]'
                    : 'text-[var(--cos-muted)] hover:bg-[var(--cos-grain)] hover:text-[var(--cos-text)]',
                ].join(' ')
              }
            >
              <Icon size={14} aria-hidden />
              {label}
            </NavLink>
          ))}
        </nav>
        <ThemeToggle />
      </header>
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <div className="min-h-0 min-w-0 flex-1 overflow-hidden">
          <Outlet />
        </div>
        {showInspector && (
          <aside
            className="hidden w-[320px] shrink-0 overflow-auto border-l border-[var(--cos-border)] bg-[var(--cos-panel)] text-[var(--cos-text)] md:block"
            aria-label="Inspector"
          >
            <Inspector />
          </aside>
        )}
      </div>
    </div>
  );
}
