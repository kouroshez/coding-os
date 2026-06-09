import { NavLink, Outlet, useParams } from 'react-router-dom';
import {
  LayoutDashboard,
  HeartPulse,
  FileText,
  Activity,
  Users,
  Settings,
  Brain,
} from 'lucide-react';
import { SubNav, subNavTabClass } from '@/layout/HubPrimitives';

export default function DiagnosticsPage() {
  const { slug } = useParams<{ slug?: string }>();

  const linkFor = (subPath: string) =>
    slug ? `/p/${encodeURIComponent(slug)}/diagnostics/${subPath}` : `/diagnostics/${subPath}`;

  const tabs = [
    { path: 'overview', label: 'Overview', Icon: LayoutDashboard },
    { path: 'doctor', label: 'Doctor', Icon: HeartPulse },
    { path: 'logs', label: 'Logs', Icon: FileText },
    { path: 'observability', label: 'Observability', Icon: Activity },
    { path: 'sessions', label: 'Sessions', Icon: Users },
    { path: 'memory', label: 'Memory', Icon: Brain },
    { path: 'settings', label: 'Settings', Icon: Settings },
  ];

  return (
    <div className="flex h-full w-full flex-col overflow-hidden">
      <SubNav right={<span className="text-[11px] tracking-tight text-[var(--cos-faint)]">Diagnostics</span>}>
        {tabs.map((tab) => (
          <NavLink
            key={tab.path}
            to={linkFor(tab.path)}
            className={({ isActive }) => subNavTabClass(isActive)}
          >
            <tab.Icon size={14} aria-hidden />
            <span>{tab.label}</span>
          </NavLink>
        ))}
      </SubNav>

      {/* Content Pane */}
      <div className="min-h-0 flex-1 overflow-hidden">
        <Outlet />
      </div>
    </div>
  );
}
