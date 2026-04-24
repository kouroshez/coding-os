import { useApiGet } from '@/lib/hooks';

interface TraceEvent {
  kind?: string;
  timestamp?: string;
  formula_id?: string;
  summary?: string;
  raw?: string;
  [key: string]: unknown;
}

interface TracePayload {
  session_id: string;
  events: TraceEvent[];
  count: number;
}

const EVENT_COLORS: Record<string, string> = {
  dispatch: '#7fd4a0',
  supervise: '#5aa8ff',
  supervise_record: '#5aa8ff',
  backtrack: '#ef4444',
  compose_chain: '#c68fff',
  analyze_task: '#fbbf24',
};

// Right pane: vertical timeline of the selected session's events.
export default function TraceTimeline({ sessionId }: { sessionId: string }) {
  const { data, isLoading, error } = useApiGet<TracePayload>(
    ['cognition-trace', sessionId],
    `/api/cognition/trace/${encodeURIComponent(sessionId)}`,
  );

  if (isLoading) return <p className="p-4 text-sm text-[var(--cos-muted)]">loading events…</p>;
  if (error)
    return (
      <p role="alert" className="p-4 text-sm text-rose-400">
        {error.message}
      </p>
    );
  if (!data || data.events.length === 0)
    return <p className="p-4 text-sm text-[var(--cos-muted)]">no events in this session.</p>;

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-[var(--cos-border)] px-4 py-2 text-xs">
        <h2 className="font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
          {data.session_id}
        </h2>
        <p className="text-[var(--cos-muted)]">{data.count} events</p>
      </header>
      <ol className="flex-1 overflow-auto p-3 cos-scroll">
        {data.events.map((e, i) => {
          const kind = e.kind ?? 'event';
          const dot = EVENT_COLORS[kind] ?? '#9ea4ae';
          return (
            <li
              key={i}
              className="relative mb-2 rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] p-2 text-xs"
            >
              <div className="mb-1 flex items-center gap-2">
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ background: dot }}
                  aria-hidden
                />
                <span className="font-semibold">{kind}</span>
                {e.formula_id && (
                  <span className="rounded bg-[var(--cos-border)] px-1 text-[10px] text-[var(--cos-muted)]">
                    {String(e.formula_id)}
                  </span>
                )}
                {e.timestamp && (
                  <span className="ml-auto text-[10px] text-[var(--cos-muted)]">
                    {String(e.timestamp)}
                  </span>
                )}
              </div>
              {e.summary && <p className="text-[var(--cos-text)]">{String(e.summary)}</p>}
              {!e.summary && e.raw && (
                <pre className="overflow-auto text-[10px] text-[var(--cos-muted)] cos-scroll">
                  {String(e.raw)}
                </pre>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
