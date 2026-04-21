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

  if (isLoading) return <p className="p-4 text-sm text-[#9ea4ae]">loading events…</p>;
  if (error)
    return (
      <p role="alert" className="p-4 text-sm text-rose-400">
        {error.message}
      </p>
    );
  if (!data || data.events.length === 0)
    return <p className="p-4 text-sm text-[#9ea4ae]">no events in this session.</p>;

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-[#2a2f39] px-4 py-2 text-xs">
        <h2 className="font-semibold uppercase tracking-wide text-[#9ea4ae]">
          {data.session_id}
        </h2>
        <p className="text-[#9ea4ae]">{data.count} events</p>
      </header>
      <ol className="flex-1 overflow-auto p-3 cos-scroll">
        {data.events.map((e, i) => {
          const kind = e.kind ?? 'event';
          const dot = EVENT_COLORS[kind] ?? '#9ea4ae';
          return (
            <li
              key={i}
              className="relative mb-2 rounded border border-[#2a2f39] bg-[#0e1116] p-2 text-xs"
            >
              <div className="mb-1 flex items-center gap-2">
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ background: dot }}
                  aria-hidden
                />
                <span className="font-semibold">{kind}</span>
                {e.formula_id && (
                  <span className="rounded bg-[#2a2f39] px-1 text-[10px] text-[#9ea4ae]">
                    {String(e.formula_id)}
                  </span>
                )}
                {e.timestamp && (
                  <span className="ml-auto text-[10px] text-[#6c7280]">
                    {String(e.timestamp)}
                  </span>
                )}
              </div>
              {e.summary && <p className="text-[#c8ccd4]">{String(e.summary)}</p>}
              {!e.summary && e.raw && (
                <pre className="overflow-auto text-[10px] text-[#6c7280] cos-scroll">
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
