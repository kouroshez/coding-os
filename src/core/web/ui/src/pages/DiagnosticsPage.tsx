import { NavLink, Outlet, useParams } from 'react-router-dom';
import { HeartPulse, FileText, Activity, Users, Settings, ShieldCheck, Brain } from 'lucide-react';

export default function DiagnosticsPage() {
  const { slug } = useParams<{ slug?: string }>();

  const linkFor = (subPath: string) =>
    slug ? `/p/${encodeURIComponent(slug)}/diagnostics/${subPath}` : `/diagnostics/${subPath}`;

  const tabs = [
    { path: 'doctor', label: 'Doctor', Icon: HeartPulse },
    { path: 'logs', label: 'Logs', Icon: FileText },
    { path: 'observability', label: 'Observability', Icon: Activity },
    { path: 'sessions', label: 'Sessions', Icon: Users },
    { path: 'audits', label: 'Audits', Icon: ShieldCheck },
    { path: 'memory', label: 'Memory', Icon: Brain },
    { path: 'settings', label: 'Settings', Icon: Settings },
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
                    'flex items-center gap-2 rounded-full px-4 py-1.5 text-[11px] font-bold tracking-wide uppercase transition-all duration-300',
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
            Diagnostics Hub
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
