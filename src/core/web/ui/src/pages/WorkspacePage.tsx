import { NavLink, Outlet, useParams } from 'react-router-dom';
import { LayoutDashboard, MessageSquare, KanbanSquare, Search, Brain, Palette } from 'lucide-react';
import { SubNav, subNavTabClass } from '@/layout/HubPrimitives';

export default function WorkspacePage() {
  const { slug } = useParams<{ slug?: string }>();

  const linkFor = (subPath: string) =>
    slug ? `/p/${encodeURIComponent(slug)}/workspace/${subPath}` : `/workspace/${subPath}`;

  const tabs = [
    { path: 'overview', label: 'Overview', Icon: LayoutDashboard },
    { path: 'chat', label: 'Chat', Icon: MessageSquare },
    { path: 'board', label: 'Board', Icon: KanbanSquare },
    { path: 'search', label: 'Search', Icon: Search },
    { path: 'memory', label: 'Memory', Icon: Brain },
    { path: 'design', label: 'Design', Icon: Palette },
  ];

  return (
    <div className="flex h-full w-full flex-col overflow-hidden">
      <SubNav right={<span className="text-[11px] tracking-tight text-[var(--cos-faint)]">Workspace</span>}>
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
