import { useMemo, useState } from 'react';
import { useApiGet } from '@/lib/hooks';

interface SessionRef {
  agent: string;
  session_id: string;
  size_bytes: number;
  mtime_ts?: number;
  event_count?: number;
  first_event_kind?: string | null;
}

interface TracesPayload {
  sessions: SessionRef[];
  count: number;
}

// Parse a session_id of the canonical shape:
//   ses-<agent>-YYYYMMDD-HHMMSS-<rand>
// → "2026-04-25 11:42". Falls back to the raw id when the pattern
// doesn't match (e.g. "anon", "c-sess-05", "ses-bt-1").
function parseSessionDate(sessionId: string): string | null {
  const m = /^ses-[^-]+-(\d{8})-(\d{6})/.exec(sessionId);
  if (!m) return null;
  const date = m[1];
  const time = m[2];
  return `${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)} ${time.slice(0, 2)}:${time.slice(2, 4)}`;
}

function formatRelative(ts: number | undefined): string | null {
  if (!ts) return null;
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 86400 * 30) return `${Math.floor(diff / 86400)}d ago`;
  return new Date(ts * 1000).toLocaleDateString();
}

export default function TraceList({
  selected,
  onSelect,
}: {
  selected: string | null;
  onSelect: (sessionId: string, agent: string) => void;
}) {
  const { data, isLoading, error } = useApiGet<TracesPayload>(
    ['cognition-traces'],
    '/api/cognition/traces',
    undefined,
    { refetchIntervalMs: 5000 },
  );
  const [agentFilter, setAgentFilter] = useState<string>('all');
  const [query, setQuery] = useState('');

  const allSessions = data?.sessions ?? [];
  const agents = useMemo(() => {
    const s = new Set(allSessions.map((x) => x.agent));
    return Array.from(s).sort();
  }, [allSessions]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return allSessions
      .filter((s) => agentFilter === 'all' || s.agent === agentFilter)
      .filter((s) => !q || s.session_id.toLowerCase().includes(q))
      .sort((a, b) => (b.mtime_ts ?? 0) - (a.mtime_ts ?? 0));
  }, [allSessions, agentFilter, query]);

  return (
    <section aria-label="Cognition traces" className="flex h-full min-h-0 flex-col">
      <header className="border-b border-[var(--cos-border)] px-3 py-2">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
            Traces
          </h2>
          <span className="text-[10px] text-[var(--cos-muted)]">
            {filtered.length} / {allSessions.length}
          </span>
        </div>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="filter by session id"
          aria-label="Filter sessions"
          className="mb-2 w-full rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1 text-xs"
        />
        <div className="flex flex-wrap gap-1">
          <FilterChip label={`all (${allSessions.length})`} active={agentFilter === 'all'} onClick={() => setAgentFilter('all')} />
          {agents.map((a) => {
            const count = allSessions.filter((s) => s.agent === a).length;
            return (
              <FilterChip key={a} label={`${a} (${count})`} active={agentFilter === a} onClick={() => setAgentFilter(a)} />
            );
          })}
        </div>
      </header>
      <div className="flex-1 overflow-auto cos-scroll">
        {isLoading && <p className="p-3 text-xs text-[var(--cos-muted)]">loading traces…</p>}
        {error && (
          <p role="alert" className="p-3 text-xs text-rose-400">
            {error.message}
          </p>
        )}
        {!isLoading && !error && filtered.length === 0 && (
          <p className="p-3 text-xs text-[var(--cos-muted)]">no traces match filter.</p>
        )}
        <ul>
          {filtered.map((s) => {
            const active = s.session_id === selected;
            const friendly = parseSessionDate(s.session_id);
            const ago = formatRelative(s.mtime_ts);
            return (
              <li key={`${s.agent}/${s.session_id}`}>
                <button
                  type="button"
                  onClick={() => onSelect(s.session_id, s.agent)}
                  aria-pressed={active}
                  className={[
                    'block w-full border-b border-[var(--cos-border)]/60 px-3 py-2 text-left text-xs',
                    active
                      ? 'bg-[var(--cos-accent)]/15 text-[var(--cos-accent)]'
                      : 'text-[var(--cos-text)] hover:bg-[var(--cos-accent)]/5',
                  ].join(' ')}
                >
                  <div className="flex items-center gap-2">
                    <span className="rounded border border-[var(--cos-border)] px-1 py-0.5 text-[9px] uppercase tracking-wider text-[var(--cos-muted)]">
                      {s.agent}
                    </span>
                    {s.first_event_kind && (
                      <span className="text-[9px] text-[var(--cos-muted)]">{s.first_event_kind}</span>
                    )}
                    {ago && <span className="ml-auto text-[9px] text-[var(--cos-muted)]">{ago}</span>}
                  </div>
                  <div className="mt-1 truncate font-semibold">
                    {friendly ?? s.session_id}
                  </div>
                  <div className="mt-0.5 flex items-center justify-between text-[10px] text-[var(--cos-muted)]">
                    <span className="truncate font-mono">{s.session_id}</span>
                    <span className="ml-2 shrink-0">
                      {s.event_count != null ? `${s.event_count}ev` : ''} · {(s.size_bytes / 1024).toFixed(1)}kb
                    </span>
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

function FilterChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        'rounded border px-2 py-0.5 text-[10px] transition-colors',
        active
          ? 'border-[var(--cos-accent)] bg-[var(--cos-accent)]/10 text-[var(--cos-accent)]'
          : 'border-[var(--cos-border)] text-[var(--cos-muted)] hover:border-[var(--cos-accent)]',
      ].join(' ')}
    >
      {label}
    </button>
  );
}
