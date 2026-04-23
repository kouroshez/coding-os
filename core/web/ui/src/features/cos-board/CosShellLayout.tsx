import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { Brain, KanbanSquare, Network, Search } from 'lucide-react';
import Inspector from '@/layout/Inspector';

const NAV = [
  { to: '/board', label: 'Board', Icon: KanbanSquare },
  { to: '/graph', label: 'Graph', Icon: Network },
  { to: '/search', label: 'Search', Icon: Search },
  { to: '/cognition', label: 'Cognition', Icon: Brain },
] as const;

export default function CosShellLayout() {
  const location = useLocation();
  const showInspector =
    location.pathname.startsWith('/graph') ||
    location.pathname.startsWith('/search') ||
    location.pathname.startsWith('/cognition');

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
        <nav className="flex flex-1 flex-wrap items-center gap-1" aria-label="Primary">
          {NAV.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/board' || to === '/search'}
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
