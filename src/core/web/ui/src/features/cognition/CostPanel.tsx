import { useApiGet } from '@/lib/hooks';

interface CostRow {
  formula_id: string;
  day: string;
  total_cost_usd: number;
  count: number;
  avg_latency_ms: number | null;
}

interface CostPayload {
  rows: CostRow[];
  total_usd: number;
  count: number;
}

interface DispatchRow {
  session_id: string;
  formula_id: string;
  ts: string;
  cost_usd: number | null;
  budget_usd: number | null;
  status: string | null;
  latency_ms: number | null;
}

interface DispatchersPayload {
  dispatches: DispatchRow[];
  count: number;
}

export default function CostPanel({ onPick }: { onPick: (sessionId: string) => void }) {
  const cost = useApiGet<CostPayload>(['cognition-cost'], '/api/cognition/cost', { limit: 30 }, {
    refetchIntervalMs: 10000,
  });
  const dispatchers = useApiGet<DispatchersPayload>(
    ['cognition-dispatchers'],
    '/api/cognition/dispatchers',
    { limit: 25 },
    { refetchIntervalMs: 10000 },
  );

  const todayKey = new Date().toISOString().slice(0, 10);
  const today = (cost.data?.rows ?? []).filter((r) => r.day === todayKey);
  const todayTotal = today.reduce((acc, r) => acc + (r.total_cost_usd || 0), 0);

  return (
    <section aria-label="Dispatch cost" className="flex h-full min-h-0 flex-col">
      <header className="border-b border-[var(--cos-border)] px-3 py-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
          Dispatch cost
        </h2>
        <p className="mt-1 text-[10px] text-[var(--cos-muted)]">
          today ${todayTotal.toFixed(4)} · all-time ${(cost.data?.total_usd ?? 0).toFixed(4)}
        </p>
      </header>
      <div className="flex-1 overflow-auto cos-scroll p-3 text-xs">
        {cost.isLoading && <p className="text-[var(--cos-muted)]">loading cost…</p>}
        {cost.error && <p className="text-rose-400">{cost.error.message}</p>}
        {!cost.isLoading && !cost.error && (cost.data?.rows.length ?? 0) === 0 && (
          <p className="text-[var(--cos-muted)]">no dispatch cost recorded yet.</p>
        )}
        {(cost.data?.rows.length ?? 0) > 0 && (
          <div className="mb-4">
            <h3 className="mb-1 text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">
              by day · formula
            </h3>
            <ul className="space-y-1">
              {(cost.data?.rows ?? []).map((r) => (
                <li
                  key={`${r.day}-${r.formula_id}`}
                  className="flex items-center gap-2 rounded border border-[var(--cos-border)] bg-[var(--cos-panel)] px-2 py-1"
                >
                  <span className="font-mono text-[10px] text-[var(--cos-muted)]">{r.day}</span>
                  <span className="rounded bg-[var(--cos-accent)]/10 px-1 text-[10px] text-[var(--cos-accent)]">
                    {r.formula_id}
                  </span>
                  <span className="ml-auto font-mono">{(r.total_cost_usd || 0).toFixed(4)}$</span>
                  <span className="text-[10px] text-[var(--cos-muted)]">{r.count}×</span>
                  {r.avg_latency_ms != null && (
                    <span className="text-[10px] text-[var(--cos-muted)]">
                      {Math.round(r.avg_latency_ms)}ms
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        <h3 className="mb-1 text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">
          recent dispatches
        </h3>
        {dispatchers.isLoading && <p className="text-[var(--cos-muted)]">loading dispatches…</p>}
        {dispatchers.error && <p className="text-rose-400">{dispatchers.error.message}</p>}
        {!dispatchers.isLoading && (dispatchers.data?.dispatches.length ?? 0) === 0 && (
          <p className="text-[var(--cos-muted)]">no recent dispatches.</p>
        )}
        <ul className="space-y-1">
          {(dispatchers.data?.dispatches ?? []).map((d) => (
            <li key={`${d.session_id}-${d.ts}`}>
              <button
                type="button"
                onClick={() => onPick(d.session_id)}
                className="block w-full rounded border border-[var(--cos-border)] bg-[var(--cos-panel)] px-2 py-1 text-left transition-colors hover:border-[var(--cos-accent)]"
              >
                <div className="flex items-center gap-2">
                  <span className="rounded bg-[var(--cos-accent)]/10 px-1 text-[10px] text-[var(--cos-accent)]">
                    {d.formula_id}
                  </span>
                  {d.status && <StatusBadge status={d.status} />}
                  {d.cost_usd != null && (
                    <span className="ml-auto font-mono text-[10px]">${d.cost_usd.toFixed(4)}</span>
                  )}
                </div>
                <div className="mt-0.5 truncate font-mono text-[10px] text-[var(--cos-muted)]">
                  {d.session_id}
                </div>
                <div className="mt-0.5 flex justify-between text-[10px] text-[var(--cos-muted)]">
                  <span>{d.ts}</span>
                  {d.latency_ms != null && <span>{d.latency_ms}ms</span>}
                </div>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function StatusBadge({ status }: { status: string }) {
  const palette: Record<string, string> = {
    completed: 'bg-emerald-500/15 text-emerald-300',
    success: 'bg-emerald-500/15 text-emerald-300',
    failed: 'bg-rose-500/15 text-rose-300',
    error: 'bg-rose-500/15 text-rose-300',
    timeout: 'bg-amber-500/15 text-amber-300',
    started: 'bg-sky-500/15 text-sky-300',
    running: 'bg-sky-500/15 text-sky-300',
  };
  const cls = palette[status] ?? 'bg-[var(--cos-border)]/30 text-[var(--cos-muted)]';
  return (
    <span className={['rounded px-1 text-[10px] uppercase tracking-wide', cls].join(' ')}>{status}</span>
  );
}
