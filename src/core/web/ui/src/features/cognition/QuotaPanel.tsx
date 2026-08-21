import { useApiGet } from '@/lib/hooks';

// Producer: src/core/web/routes/cognition_account_views.py::provider_quota,
// shaped by thinking_os/account_status.py::AccountReport. Field names copied
// from the dataclass, not guessed (api-contract-discipline).
interface QuotaWindow {
  label: string;
  percent: number;
  resets_at: string | null;
  severity: string;
  window_minutes: number | null;
  scope: string | null;
}

interface AdapterQuota {
  adapter: string;
  status: string;
  reason: string;
  auth_mode: string;
  plan: string;
  source: string;
  observed_at: string | null;
  age_seconds: number | null;
  stale: boolean;
  windows: QuotaWindow[];
}

interface QuotaPayload {
  adapters: AdapterQuota[];
  tightest: (QuotaWindow & { adapter: string }) | null;
  checked_at: string;
}

// A provider that publishes a severity has the last word on its own plan; the
// thresholds only fill in for one that publishes none, so the two never
// disagree about the same window.
function toneOf(w: QuotaWindow): string {
  if (w.severity === 'critical' || w.percent >= 90) return 'var(--cos-err)';
  if (w.severity === 'warning' || w.percent >= 70) return 'var(--cos-warn)';
  return 'var(--cos-ok)';
}

export function humanizeAge(seconds: number | null): string {
  if (seconds == null) return 'unknown age';
  if (seconds < 90) return `${seconds}s ago`;
  if (seconds < 5400) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 172800) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

export function humanizeReset(iso: string | null, now: number = Date.now()): string {
  if (!iso) return '';
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return '';
  const seconds = Math.round((at - now) / 1000);
  if (seconds <= 0) return 'resetting';
  if (seconds < 5400) return `resets in ${Math.round(seconds / 60)}m`;
  if (seconds < 172800) return `resets in ${Math.round(seconds / 3600)}h`;
  return `resets in ${Math.round(seconds / 86400)}d`;
}

export default function QuotaPanel() {
  const quota = useApiGet<QuotaPayload>(['cognition-quota'], '/api/cognition/quota', undefined, {
    refetchIntervalMs: 30000,
  });
  const adapters = quota.data?.adapters ?? [];

  return (
    <section aria-label="Provider quota" className="border-b border-[var(--cos-border)]">
      <header className="px-3 py-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
          Provider quota
        </h2>
        {quota.data?.tightest && (
          <p className="mt-1 text-[10px] text-[var(--cos-muted)]">
            tightest: {quota.data.tightest.adapter} {quota.data.tightest.label}{' '}
            {quota.data.tightest.percent}%
          </p>
        )}
      </header>
      <div className="px-3 pb-3 text-xs">
        {quota.isLoading && <p className="text-[var(--cos-muted)]">reading provider state…</p>}
        {quota.error && <p className="text-[var(--cos-err)]">{quota.error.message}</p>}
        {!quota.isLoading && !quota.error && adapters.length === 0 && (
          <p className="text-[var(--cos-muted)]">no adapter reports a quota window.</p>
        )}
        <ul className="space-y-2">
          {adapters.map((a) => (
            <li key={a.adapter}>
              <div className="flex items-center gap-2">
                <span className="rounded bg-[var(--cos-accent)]/10 px-1 text-[10px] text-[var(--cos-accent)]">
                  {a.adapter}
                </span>
                {a.plan && <span className="text-[10px] text-[var(--cos-muted)]">{a.plan}</span>}
                {a.auth_mode !== 'unknown' && (
                  <span className="text-[10px] text-[var(--cos-muted)]">· {a.auth_mode}</span>
                )}
                {a.status === 'ok' && (
                  // Age is always shown, not only when stale: a percentage with
                  // no timestamp invites the reader to assume it is live.
                  <span
                    className={`ml-auto text-[10px] ${a.stale ? 'text-[var(--cos-warn)]' : 'text-[var(--cos-muted)]'}`}
                    title={`read from ${a.source}`}
                  >
                    {humanizeAge(a.age_seconds)}
                    {a.stale ? ' · stale' : ''}
                  </span>
                )}
              </div>
              {a.status !== 'ok' ? (
                <p className="mt-1 text-[10px] text-[var(--cos-muted)]">{a.reason}</p>
              ) : (
                <ul className="mt-1 space-y-1">
                  {a.windows.map((w) => (
                    <li key={`${a.adapter}-${w.label}`}>
                      <div className="flex items-center gap-2">
                        <span className="w-28 shrink-0 truncate text-[10px] text-[var(--cos-muted)]">
                          {w.label}
                        </span>
                        <div
                          className="h-1.5 flex-1 overflow-hidden rounded bg-[var(--cos-border)]"
                          role="meter"
                          aria-valuenow={w.percent}
                          aria-valuemin={0}
                          aria-valuemax={100}
                          aria-label={`${a.adapter} ${w.label} used`}
                        >
                          <div
                            className="h-full rounded"
                            style={{
                              width: `${Math.min(100, Math.max(0, w.percent))}%`,
                              background: toneOf(w),
                            }}
                          />
                        </div>
                        <span className="w-9 shrink-0 text-right font-mono text-[10px]">
                          {w.percent}%
                        </span>
                      </div>
                      {w.resets_at && (
                        <p className="pl-[7.5rem] text-[10px] text-[var(--cos-muted)]">
                          {humanizeReset(w.resets_at)}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
