import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Folder, ListTodo, MessageSquare } from 'lucide-react';
import { Modal } from '@/components/Modal';
import { apiGet } from '@/lib/api-client';
import { useScopedLink } from '@/lib/use-scoped-link';

export interface CommandItem {
  type: 'project' | 'task' | 'chat';
  id: string;
  label: string;
  sub?: string;
  target: string;
}

/** Pure: case-insensitive substring filter over label+sub (exported for tests). */
export function filterCommandItems(items: CommandItem[], query: string): CommandItem[] {
  const q = query.trim().toLowerCase();
  if (!q) return items;
  return items.filter((it) => `${it.label} ${it.sub ?? ''}`.toLowerCase().includes(q));
}

const ICON = { project: Folder, task: ListTodo, chat: MessageSquare } as const;

interface ProjectsResp {
  projects?: { slug: string; path?: string }[];
}
interface BoardResp {
  cards?: { task_id: string; title?: string; status?: string }[];
}
interface ChatsResp {
  sessions?: { session_id?: string; summary?: string; custom_title?: string }[];
}

/** Global Cmd/Ctrl+K jump-to over projects, tasks and chat sessions. */
export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<CommandItem[]>([]);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { scopedLink } = useScopedLink();

  // Reserve Cmd/Ctrl+K globally.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Fetch sources when opened; reset transient state.
  useEffect(() => {
    if (!open) return;
    setQuery('');
    setActive(0);
    inputRef.current?.focus();
    let cancelled = false;
    void (async () => {
      const next: CommandItem[] = [];
      try {
        const [projects] = await apiGet<ProjectsResp>('/api/hub/projects');
        for (const p of projects.projects ?? []) {
          next.push({
            type: 'project',
            id: p.slug,
            label: p.slug,
            sub: p.path,
            target: `/p/${encodeURIComponent(p.slug)}/workspace/chat`,
          });
        }
      } catch {
        /* projects unavailable — skip that group */
      }
      try {
        const [board] = await apiGet<BoardResp>('/api/board/list');
        for (const c of board.cards ?? []) {
          next.push({
            type: 'task',
            id: c.task_id,
            label: `${c.task_id} ${c.title ?? ''}`.trim(),
            sub: c.status,
            target: scopedLink('workspace/board'),
          });
        }
      } catch {
        /* board unavailable — skip */
      }
      try {
        const [chats] = await apiGet<ChatsResp>('/api/cognition/chats', { limit: 50 });
        for (const s of chats.sessions ?? []) {
          const sid = s.session_id;
          if (!sid) continue;
          next.push({
            type: 'chat',
            id: sid,
            label: s.custom_title ?? s.summary ?? sid,
            sub: 'chat session',
            target: scopedLink('workspace/chat', encodeURIComponent(sid)),
          });
        }
      } catch {
        /* chats unavailable — skip */
      }
      if (!cancelled) setItems(next);
    })();
    return () => {
      cancelled = true;
    };
  }, [open, scopedLink]);

  const results = useMemo(() => filterCommandItems(items, query), [items, query]);

  const select = useCallback(
    (item: CommandItem | undefined) => {
      if (!item) return;
      setOpen(false);
      navigate(item.target);
    },
    [navigate],
  );

  const onInputKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, Math.max(results.length - 1, 0)));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      select(results[active]);
    }
  };

  if (!open) return null;

  return (
    <Modal open={open} onClose={() => setOpen(false)} title="Jump to…" size="md">
      <div className="flex flex-col gap-3">
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
          }}
          onKeyDown={onInputKey}
          placeholder="Search projects, tasks, chats…"
          aria-label="Command palette search"
          dir="auto"
          className="w-full rounded border border-[var(--cos-border)] bg-black/20 px-3 py-2 text-[13px] text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
        />
        <ul className="max-h-80 overflow-auto" role="listbox" aria-label="Results">
          {results.length === 0 ? (
            <li className="px-2 py-4 text-center text-[12px] text-[var(--cos-faint)]">No matches</li>
          ) : (
            results.map((it, i) => {
              const Icon = ICON[it.type];
              return (
                <li key={`${it.type}:${it.id}`} role="option" aria-selected={i === active}>
                  <button
                    type="button"
                    onMouseEnter={() => setActive(i)}
                    onClick={() => select(it)}
                    className={[
                      'flex w-full items-center gap-2 rounded px-2 py-2 text-left text-[13px]',
                      i === active ? 'bg-[var(--cos-grain)]' : 'hover:bg-[var(--cos-grain)]',
                    ].join(' ')}
                  >
                    <Icon size={14} className="shrink-0 text-[var(--cos-muted)]" aria-hidden />
                    <span className="min-w-0 flex-1 truncate text-[var(--cos-text)]" dir="auto">
                      {it.label}
                    </span>
                    {it.sub && (
                      <span className="shrink-0 text-[10px] text-[var(--cos-faint)]">{it.sub}</span>
                    )}
                  </button>
                </li>
              );
            })
          )}
        </ul>
      </div>
    </Modal>
  );
}
