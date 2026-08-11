import { Section } from './DoctorPrimitives';
import { StatTile } from '@/lib/charts';
import { useApiGet } from '@/lib/hooks';
import type { DbHealthPayload } from './doctor-types';

export function SqliteTab() {
  const db = useApiGet<DbHealthPayload>(['api-health-db'], '/api/health/db', undefined, {
    refetchIntervalMs: 10000,
  });
  if (db.isLoading) return <p className="text-xs text-[var(--cos-muted)]">reading sqlite…</p>;
  if (db.error) return <p className="text-xs text-[var(--cos-err)]">{db.error.message}</p>;
  if (!db.data) return null;
  const tables = Object.entries(db.data.tables ?? {});
  const presentTables = tables.filter(([, v]) => typeof v === 'number');
  const totalRows = presentTables.reduce((acc, [, v]) => acc + (v as number), 0);
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <StatTile label="DB present" value={db.data.exists ? 'yes' : 'no'} tone={db.data.exists ? 'ok' : 'danger'} />
      <StatTile label="Size" value={db.data.exists ? `${(db.data.size_bytes / 1024).toFixed(1)} kB` : '—'} tone="neutral" />
      <StatTile label="Tables present" value={presentTables.length} tone={presentTables.length > 0 ? 'ok' : 'warn'} />
      <StatTile label="Total rows" value={totalRows} tone="neutral" />
      {(db.data.diagnostics?.length ?? 0) > 0 && (
        <Section title="⚠️ Diagnostics — why a loop may be dead" cols="md:col-span-4">
          <ul className="space-y-1.5 text-[11px] text-[var(--cos-warn)]">
            {db.data.diagnostics!.map((d, i) => (
              <li key={i} className="flex gap-2">
                <span aria-hidden>•</span>
                <span>{d}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}
      <Section title="Rows by table" cols="md:col-span-4">
        {tables.length === 0 ? (
          <p className="text-[11px] text-[var(--cos-muted)]">no tables reported.</p>
        ) : (
          <table className="w-full text-[11px]">
            <thead className="text-left text-[var(--cos-muted)]">
              <tr>
                <th className="py-1 pr-2">table</th>
                <th className="py-1 pr-2 text-right">rows</th>
              </tr>
            </thead>
            <tbody>
              {tables.map(([t, v]) => {
                const isError = typeof v === 'object' && v !== null && 'error' in v;
                const missing = v == null;
                const display = missing
                  ? <span className="text-[var(--cos-faint)]">absent</span>
                  : isError
                  ? <span className="text-[var(--cos-err)]">{(v as { error: string }).error}</span>
                  : <span className="font-mono">{String(v)}</span>;
                return (
                  <tr key={t}>
                    <td className="border-t border-[var(--cos-border)] py-1 pr-2 font-mono">{t}</td>
                    <td className="border-t border-[var(--cos-border)] py-1 pr-2 text-right">{display}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Section>
      <Section title="DB path" cols="md:col-span-4">
        <p dir="ltr" className="break-all font-mono text-[10px] text-[var(--cos-muted)]">{db.data.db_path}</p>
        {db.data.error && <p className="mt-1 text-[10px] text-[var(--cos-err)]">{db.data.error}</p>}
      </Section>
    </div>
  );
}

