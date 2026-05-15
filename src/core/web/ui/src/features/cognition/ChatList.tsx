import { useMemo, useState } from 'react';
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
}: {
  selected: string | null;
  onSelect: (sessionId: string) => void;
}) {
  const { data, isLoading, error } = useApiGet<ChatsPayload>(
    ['cognition-chats'],
    '/api/cognition/chats',
    { limit: 100 },
    { refetchIntervalMs: 10_000 },
  );
  const [query, setQuery] = useState('');

  const sessions = data?.sessions ?? [];
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter((s) => {
      const hay = [s.session_id, s.summary, s.custom_title, s.first_prompt, s.git_branch]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return hay.includes(q);
    });
  }, [sessions, query]);

  return (
    <section aria-label="Chat sessions" className="flex h-full min-h-0 flex-col">
      <header className="border-b border-[var(--cos-border)] px-3 py-2">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
            Chats
          </h2>
          <span className="text-[10px] text-[var(--cos-muted)]">
            {filtered.length} / {sessions.length}
          </span>
        </div>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="filter by title / prompt / id"
          aria-label="Filter chats"
          className="w-full rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1 text-xs"
        />
      </header>
      <div className="flex-1 overflow-auto cos-scroll">
        {isLoading && <p className="p-3 text-xs text-[var(--cos-muted)]">loading chats…</p>}
        {error && (
          <p role="alert" className="p-3 text-xs text-rose-400">
            {error.message}
          </p>
        )}
        {!isLoading && !error && filtered.length === 0 && (
          <p className="p-3 text-xs text-[var(--cos-muted)]">no chat sessions match filter.</p>
        )}
        <ul>
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
                    'block w-full border-b border-[var(--cos-border)]/60 px-3 py-2 text-left text-xs',
                    active
                      ? 'bg-[var(--cos-accent)]/15 text-[var(--cos-accent)]'
                      : 'text-[var(--cos-text)] hover:bg-[var(--cos-accent)]/5',
                  ].join(' ')}
                >
                  <div className="flex items-center gap-2">
                    {s.git_branch && (
                      <span className="rounded border border-[var(--cos-border)] px-1 py-0.5 text-[9px] uppercase tracking-wider text-[var(--cos-muted)]">
                        {s.git_branch}
                      </span>
                    )}
                    {ago && <span className="ml-auto text-[9px] text-[var(--cos-muted)]">{ago}</span>}
                  </div>
                  <div className="mt-1 line-clamp-2 font-semibold">{title}</div>
                  <div className="mt-0.5 flex items-center justify-between text-[10px] text-[var(--cos-muted)]">
                    <span className="truncate font-mono">{s.session_id.slice(0, 8)}…</span>
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
