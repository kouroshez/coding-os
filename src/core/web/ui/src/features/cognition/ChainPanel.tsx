import { useApiGet } from '@/lib/hooks';

interface ChainPayload {
  agent: string;
  chain: string[];
  active_formula: string | null;
  has_active_session: boolean;
}

export default function ChainPanel({ agent = 'claude' }: { agent?: string }) {
  const { data, isLoading, error } = useApiGet<ChainPayload>(
    ['roles-chain', agent],
    '/api/roles/chain',
    { agent },
    { refetchIntervalMs: 5000 },
  );

  return (
    <section aria-label="Composed chain" className="border-b border-[var(--cos-border)] px-3 py-3">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
        Chain · <span className="font-mono text-[var(--cos-text)]">{agent}</span>
      </h2>
      <div className="mt-2 text-xs">
        {isLoading && <p className="text-[var(--cos-muted)]">loading chain…</p>}
        {error && <p className="text-rose-400">{error.message}</p>}
        {!isLoading && !error && (!data || data.chain.length === 0) && (
          <p className="text-[var(--cos-muted)]">
            no chain composed for this agent yet — appears after <code>cos_compose_chain</code>.
          </p>
        )}
        {data && data.chain.length > 0 && (
          <ol className="flex flex-wrap items-center gap-1">
            {data.chain.map((fid, i) => {
              const active = fid === data.active_formula;
              return (
                <li key={`${fid}-${i}`} className="flex items-center gap-1">
                  <span
                    className={[
                      'rounded border px-1.5 py-0.5 font-mono text-[11px]',
                      active
                        ? 'border-[var(--cos-accent)] bg-[var(--cos-accent)]/15 text-[var(--cos-accent)]'
                        : 'border-[var(--cos-border)] text-[var(--cos-text)]',
                    ].join(' ')}
                  >
                    {fid}
                  </span>
                  {i < data.chain.length - 1 && (
                    <span aria-hidden className="text-[var(--cos-muted)]">→</span>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </section>
  );
}
