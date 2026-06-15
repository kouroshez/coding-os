import { NavLink, Outlet, useParams } from 'react-router-dom';
import { MessageSquare, KanbanSquare, Search, Palette } from 'lucide-react';
import { SubNav, subNavTabClass } from '@/layout/HubPrimitives';

export default function WorkspacePage() {
  const { slug } = useParams<{ slug?: string }>();

  const linkFor = (subPath: string) =>
    slug ? `/p/${encodeURIComponent(slug)}/workspace/${subPath}` : `/workspace/${subPath}`;

  const tabs = [
    { path: 'chat', label: 'Chat', Icon: MessageSquare },
    { path: 'board', label: 'Board', Icon: KanbanSquare },
    { path: 'search', label: 'Search', Icon: Search },
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
