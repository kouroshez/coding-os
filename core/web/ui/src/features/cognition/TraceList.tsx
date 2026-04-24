import { useApiGet } from '@/lib/hooks';

interface SessionRef {
  agent: string;
  session_id: string;
  size_bytes: number;
}

interface TracesPayload {
  sessions: SessionRef[];
  count: number;
}

// Left pane: all trace sessions under .coding-os/<agent>/traces/.
// Clicking bumps /cognition/:sessionId via the parent.
export default function TraceList({
  selected,
  onSelect,
}: {
  selected: string | null;
  onSelect: (sessionId: string) => void;
}) {
  const { data, isLoading, error } = useApiGet<TracesPayload>(
    ['cognition-traces'],
    '/api/cognition/traces',
  );

  return (
    <section aria-label="Cognition traces" className="flex h-full flex-col">
      <header className="border-b border-[var(--cos-border)] px-3 py-2 text-xs">
        <h2 className="font-semibold uppercase tracking-wide text-[var(--cos-muted)]">Traces</h2>
      </header>
      <div className="flex-1 overflow-auto cos-scroll">
        {isLoading && <p className="p-3 text-xs text-[var(--cos-muted)]">loading traces…</p>}
        {error && (
          <p role="alert" className="p-3 text-xs text-rose-400">
            {error.message}
          </p>
        )}
        {!isLoading && !error && data && data.sessions.length === 0 && (
          <p className="p-3 text-xs text-[var(--cos-muted)]">no traces recorded yet.</p>
        )}
        <ul>
          {data?.sessions.map((s) => {
            const active = s.session_id === selected;
            return (
              <li key={`${s.agent}/${s.session_id}`}>
                <button
                  type="button"
                  onClick={() => onSelect(s.session_id)}
                  aria-pressed={active}
                  className={[
                    'block w-full border-b border-[var(--cos-border)]/60 px-3 py-2 text-left text-xs text-[var(--cos-text)]',
                    active ? 'bg-[var(--cos-accent)]/15 text-[var(--cos-accent)]' : 'hover:bg-[var(--cos-accent)]/5',
                  ].join(' ')}
                >
                  <div className="font-mono truncate font-semibold">{s.session_id}</div>
                  <div className="text-[10px] text-[var(--cos-muted)] mt-0.5">
                    {s.agent} · {(s.size_bytes / 1024).toFixed(1)}kb
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
