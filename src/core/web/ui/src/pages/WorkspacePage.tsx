import { NavLink, Outlet, useParams } from 'react-router-dom';
import { LayoutDashboard, KanbanSquare, Search } from 'lucide-react';

export default function WorkspacePage() {
  const { slug } = useParams<{ slug?: string }>();

  const linkFor = (subPath: string) =>
    slug ? `/p/${encodeURIComponent(slug)}/workspace/${subPath}` : `/workspace/${subPath}`;

  const tabs = [
    { path: 'dashboard', label: 'Dashboard', Icon: LayoutDashboard },
    { path: 'board', label: 'Board', Icon: KanbanSquare },
    { path: 'search', label: 'Search', Icon: Search },
  ];

  return (
    <div className="flex h-full w-full flex-col overflow-hidden">
      {/* Sleek Sub-navigation Bar */}
      <div className="shrink-0 border-b border-[var(--cos-border)] bg-[var(--cos-panel)]/40 px-6 py-2.5 backdrop-blur-md">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 rounded-full border border-white/5 bg-black/15 p-1">
            {tabs.map((tab) => (
              <NavLink
                key={tab.path}
                to={linkFor(tab.path)}
                className={({ isActive }) =>
                  [
                    'flex items-center gap-2 rounded-full px-5 py-1.5 text-[11px] font-bold tracking-wide uppercase transition-all duration-300',
                    isActive
                      ? 'bg-[var(--cos-accent)] text-white shadow-lg  border border-white/10'
                      : 'text-[var(--cos-muted)] hover:text-[var(--cos-text)] hover:bg-white/5 border border-transparent',
                  ].join(' ')
                }
              >
                <tab.Icon size={13} />
                <span>{tab.label}</span>
              </NavLink>
            ))}
          </div>
          <div className="text-[10px] font-mono tracking-widest text-[var(--cos-faint)] uppercase">
            Workspace Hub
          </div>
        </div>
      </div>

      {/* Content Pane */}
      <div className="min-h-0 flex-1 overflow-hidden">
        <Outlet />
      </div>
    </div>
  );
}
