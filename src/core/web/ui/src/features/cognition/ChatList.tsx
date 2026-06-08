import { useMemo, useState } from 'react';
import { Plus } from 'lucide-react';
import { useApiGet } from '@/lib/hooks';

export interface ChatSession {
  session_id: string;
  summary?: string | null;
  custom_title?: string | null;
  first_prompt?: string | null;
  last_modified?: number | null;
  file_size?: number | null;
  git_branch?: string | null;
  cwd?: string | null;
  tag?: string | null;
}

interface ChatsPayload {
  sessions: ChatSession[];
  count: number;
  cwd: string;
}

function formatRelative(ms: number | null | undefined): string | null {
  if (!ms) return null;
  const diff = Date.now() - ms;
  if (diff < 60_000) return 'just now';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  if (diff < 30 * 86_400_000) return `${Math.floor(diff / 86_400_000)}d ago`;
  return new Date(ms).toLocaleDateString();
}

function formatSize(bytes: number | null | undefined): string {
  if (bytes == null) return '';
  if (bytes < 1024) return `${bytes}b`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}kb`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}mb`;
}

export default function ChatList({
  selected,
  onSelect,
  onNewChat,
}: {
  selected: string | null;
  onSelect: (sessionId: string) => void;
  onNewChat?: () => void;
}) {
  const { data, isLoading, error } = useApiGet<ChatsPayload>(
    ['cognition-chats'],
    '/api/cognition/chats',
    { limit: 100 },
    { refetchIntervalMs: 10_000 },
  );
  const [query, setQuery] = useState('');
  const [showSystem, setShowSystem] = useState(false);

  const sessions = data?.sessions ?? [];
  const filtered = useMemo(() => {
    let list = sessions;

    if (!showSystem) {
      list = list.filter((s) => {
        const id = s.session_id.toLowerCase();
        const title = (s.custom_title ?? '').toLowerCase();
        const prompt = (s.first_prompt ?? '').toLowerCase();

        const isSystem =
          id.includes('test') || id.includes('smoke') || id.includes('pytest') || id.includes('temp') || id.includes('tmp') ||
          title.includes('smoke test') || title.includes('pytest') || title.includes('healthcheck') || title.includes('health-check') ||
          prompt.includes('smoke test') || prompt.includes('pytest') || prompt === 'ping' || prompt === 'test' ||
          s.tag === 'system' || s.tag === 'test';

        return !isSystem;
      });
    }

    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter((s) => {
      const hay = [s.session_id, s.summary, s.custom_title, s.first_prompt, s.git_branch]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return hay.includes(q);
    });
  }, [sessions, query, showSystem]);

  return (
    <section aria-label="Chat sessions" className="flex h-full min-h-0 flex-col">
      <header className="border-b border-[var(--cos-border)] px-4 py-3 bg-[var(--cos-panel)]/40 backdrop-blur-md">
        <div className="mb-2.5 flex items-center justify-between gap-2">
          <h2 className="text-[11px] font-bold uppercase tracking-widest text-[var(--cos-muted)]">
            Chats <span className="font-normal normal-case tracking-normal text-[var(--cos-faint)]">{filtered.length}/{sessions.length}</span>
          </h2>
          {onNewChat && (
            <button
              type="button"
              onClick={onNewChat}
              className="flex shrink-0 items-center gap-1 rounded-md border border-[var(--cos-border)] px-2 py-1 text-[11px] font-medium text-[var(--cos-text)] hover:bg-white/[0.05] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
            >
              <Plus size={12} aria-hidden /> New chat
            </button>
          )}
        </div>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="filter by title / prompt / id..."
          aria-label="Filter chats"
          className="w-full rounded-md border border-[var(--cos-border)] bg-[var(--cos-bg)]/80 px-3 py-1.5 text-xs text-[var(--cos-text)] placeholder-[var(--cos-faint)] focus:outline-none focus:ring-1 focus:ring-[var(--cos-accent)] transition-all"
        />
        <label className="mt-2 flex w-fit items-center gap-1.5 cursor-pointer text-[10px] text-[var(--cos-muted)] hover:text-[var(--cos-text)] select-none">
          <input
            type="checkbox"
            checked={showSystem}
            onChange={(e) => setShowSystem(e.target.checked)}
            className="h-3.5 w-3.5 rounded border-white/10 bg-black/20 text-[var(--cos-accent)] focus:ring-0 cursor-pointer"
          />
          <span>Show system</span>
        </label>
      </header>
      <div className="flex-1 overflow-auto cos-scroll">
        {isLoading && <p className="p-4 text-xs text-[var(--cos-muted)]">loading chats…</p>}
        {error && (
          <p role="alert" className="p-4 text-xs text-[var(--cos-err)]">
            {error.message}
          </p>
        )}
        {!isLoading && !error && filtered.length === 0 && (
          <p className="p-4 text-xs text-[var(--cos-muted)]">no chat sessions match filter.</p>
        )}
        <ul className="divide-y divide-[var(--cos-border)]/20">
          {filtered.map((s) => {
            const active = s.session_id === selected;
            const title = s.custom_title ?? s.summary ?? s.first_prompt ?? s.session_id;
            const ago = formatRelative(s.last_modified);
            return (
              <li key={s.session_id}>
                <button
                  type="button"
                  onClick={() => onSelect(s.session_id)}
                  aria-pressed={active}
                  className={[
                    'block w-full px-4 py-3 text-left text-xs transition-all duration-200 border-l-2',
                    active
                      ? 'bg-[var(--cos-accent)]/10 text-[var(--cos-accent)] border-l-[var(--cos-accent)] font-semibold'
                      : 'text-[var(--cos-text)] hover:bg-white/[0.02] border-l-transparent',
                  ].join(' ')}
                >
                  <div className="flex items-center gap-2">
                    {s.git_branch && (
                      <span className="rounded border border-[var(--cos-border)] px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wider text-[var(--cos-muted)] bg-black/10">
                        {s.git_branch}
                      </span>
                    )}
                    {ago && <span className="ml-auto text-[9px] text-[var(--cos-muted)] font-mono">{ago}</span>}
                  </div>
                  <div className="mt-1.5 line-clamp-2 font-semibold text-[13px] leading-snug" dir="auto">{title}</div>
                  <div className="mt-1 flex items-center justify-between text-[10px] text-[var(--cos-muted)] font-mono">
                    <span className="truncate">{s.session_id.slice(0, 8)}…</span>
                    <span>{formatSize(s.file_size)}</span>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
