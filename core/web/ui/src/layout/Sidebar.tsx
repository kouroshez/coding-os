import { NavLink } from 'react-router-dom';
import { Network, KanbanSquare, Brain, Search } from 'lucide-react';

// Left navigation — the four MVP pages.
const NAV = [
  { to: '/graph', label: 'Graph', Icon: Network },
  { to: '/board', label: 'Board', Icon: KanbanSquare },
  { to: '/cognition', label: 'Cognition', Icon: Brain },
  { to: '/search', label: 'Search', Icon: Search },
] as const;

export default function Sidebar() {
  return (
    <nav aria-label="Primary" className="flex h-full flex-col py-2">
      <ul className="flex flex-col gap-1">
        {NAV.map(({ to, label, Icon }) => (
          <li key={to}>
            <NavLink
              to={to}
              className={({ isActive }) =>
                [
                  'flex items-center gap-3 px-4 py-2 text-sm',
                  'hover:bg-[#1b1f27]',
                  isActive
                    ? 'border-l-2 border-[#7fd4a0] bg-[#1b1f27] text-white'
                    : 'border-l-2 border-transparent text-[#c8ccd4]',
                ].join(' ')
              }
            >
              <Icon size={16} aria-hidden />
              <span>{label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
