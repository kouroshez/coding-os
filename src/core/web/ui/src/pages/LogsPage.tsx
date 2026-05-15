import { useEffect, useMemo, useRef, useState } from 'react';
import { useApiGet } from '@/lib/hooks';
import { resolveApiUrl } from '@/lib/api-client';
import { PageShell, PageHeader, StatusPill } from '@/layout/HubPrimitives';

interface LogEvent {
  ts: string;
  lvl: string;
  scope: string;
  msg: string;
  [key: string]: unknown;
}

interface RecentPayload {
  events: LogEvent[];
  count: number;
  log_path: string;
  log_size_bytes: number;
}

const LEVELS = ['debug', 'info', 'ok', 'warn', 'error', 'fatal'] as const;
type LevelFloor = (typeof LEVELS)[number];

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: '#9aa3ad',
  INFO: '#5aa8ff',
  OK: '#5fc78a',
  WARN: '#e7b94f',
  ERROR: '#ff7a7a',
  FATAL: '#ff4d4d',
};

const TAIL_CAP = 500;

function shortTime(iso: string): string {
  if (!iso || iso.length < 19) return iso;
  return iso.slice(11, 19);
}

function reservedKeys(): Set<string> {
  return new Set(['ts', 'lvl', 'scope', 'msg']);
}

function ExtrasCell({ event }: { event: LogEvent }) {
  const reserved = reservedKeys();
  const extras = Object.entries(event).filter(([k]) => !reserved.has(k));
  if (extras.length === 0) return <span className="text-[var(--cos-muted)]">—</span>;
  return (
    <span className="font-mono text-[10px] text-[var(--cos-muted)]">
      {extras.map(([k, v]) => `${k}=${String(v)}`).join('  ')}
    </span>
  );
}

export default function LogsPage() {
  const [level, setLevel] = useState<LevelFloor>('debug');
  const [scope, setScope] = useState('');
  const [search, setSearch] = useState('');
  const [since, setSince] = useState('');
  const [limit, setLimit] = useState(200);
  const [liveTail, setLiveTail] = useState(false);
  const [liveEvents, setLiveEvents] = useState<LogEvent[]>([]);
  const sourceRef = useRef<EventSource | null>(null);

  const params = useMemo(() => {
    const p: Record<string, unknown> = { level, limit };
    if (scope) p.scope = scope;
    if (search) p.search = search;
    if (since) p.since = since;
    return p;
  }, [level, scope, search, since, limit]);

  const recent = useApiGet<RecentPayload>(
    ['logs.recent'],
    '/api/logs/recent',
    params,
    { enabled: !liveTail, refetchIntervalMs: liveTail ? undefined : 4000 },
  );

  useEffect(() => {
    if (!liveTail) {
      sourceRef.current?.close();
      sourceRef.current = null;
      return;
    }
    setLiveEvents([]);
    const streamParams: Record<string, unknown> = { level };
    if (scope) streamParams.scope = scope;
    if (search) streamParams.search = search;
    const url = resolveApiUrl('/api/logs/stream', streamParams);
    const source = new EventSource(url);
    sourceRef.current = source;
    source.addEventListener('log', (ev) => {
      try {
        const parsed: LogEvent = JSON.parse((ev as MessageEvent).data);
        setLiveEvents((prev) => {
          const next = [...prev, parsed];
          return next.length > TAIL_CAP ? next.slice(-TAIL_CAP) : next;
        });
      } catch {
        // ignore malformed payload
      }
    });
    source.onerror = () => {
      // EventSource auto-reconnects on transient errors; no toast spam.
    };
    return () => {
      source.close();
      sourceRef.current = null;
    };
  }, [liveTail, level, scope, search]);

  const events = liveTail ? liveEvents : recent.data?.events ?? [];
  const count = events.length;
  const logPath = recent.data?.log_path ?? '';

  return (
    <PageShell>
      <PageHeader
        eyebrow={<StatusPill label={liveTail ? 'logs · live tail' : 'logs · tail'} dotColor={liveTail ? 'bg-emerald-400' : 'bg-amber-400'} />}
        title="Logs"
        subtitle="Structured agent + server activity from .cos.log.jsonl — filter by level, scope (glob), substring, or relative window."
      />

      <section className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-6">
        <label className="flex flex-col gap-1 text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">
          level floor
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value as LevelFloor)}
            className="rounded border border-[var(--cos-border)] bg-[var(--cos-panel)] px-2 py-1 font-mono text-xs text-[var(--cos-text)]"
          >
            {LEVELS.map((lv) => (
              <option key={lv} value={lv}>{lv}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">
          scope (glob)
          <input
            value={scope}
            onChange={(e) => setScope(e.target.value)}
            placeholder="hook.* / core.*"
            className="rounded border border-[var(--cos-border)] bg-[var(--cos-panel)] px-2 py-1 font-mono text-xs text-[var(--cos-text)]"
          />
        </label>
        <label className="flex flex-col gap-1 text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">
          msg substring
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="match…"
            className="rounded border border-[var(--cos-border)] bg-[var(--cos-panel)] px-2 py-1 font-mono text-xs text-[var(--cos-text)]"
          />
        </label>
        <label className="flex flex-col gap-1 text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">
          since (duration)
          <input
            value={since}
            onChange={(e) => setSince(e.target.value)}
            placeholder="10m / 1h"
            disabled={liveTail}
            className="rounded border border-[var(--cos-border)] bg-[var(--cos-panel)] px-2 py-1 font-mono text-xs text-[var(--cos-text)] disabled:opacity-50"
          />
        </label>
        <label className="flex flex-col gap-1 text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">
          limit
          <input
            type="number"
            min={1}
            max={2000}
            value={limit}
            disabled={liveTail}
            onChange={(e) => setLimit(Math.max(1, Math.min(2000, Number(e.target.value) || 1)))}
            className="rounded border border-[var(--cos-border)] bg-[var(--cos-panel)] px-2 py-1 font-mono text-xs text-[var(--cos-text)] disabled:opacity-50"
          />
        </label>
        <div className="flex items-end">
          <button
            type="button"
            onClick={() => setLiveTail((v) => !v)}
            className={[
              'h-[30px] w-full rounded px-3 font-mono text-xs font-semibold',
              liveTail
                ? 'bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/50'
                : 'bg-[var(--cos-grain)] text-[var(--cos-text)] ring-1 ring-[var(--cos-border)] hover:bg-[var(--cos-panel)]',
            ].join(' ')}
          >
            {liveTail ? 'live · click to stop' : 'tail live'}
          </button>
        </div>
      </section>

      <section className="mt-4 rounded border border-[var(--cos-border)] bg-[var(--cos-panel)]">
        <header className="flex items-center justify-between border-b border-[var(--cos-border)] px-3 py-2 font-mono text-[11px] text-[var(--cos-muted)]">
          <span>{count} event{count === 1 ? '' : 's'}{liveTail ? ' · streaming' : ''}</span>
          <span className="truncate" title={logPath}>{logPath || '.coding-os/.cos.log.jsonl'}</span>
        </header>
        {recent.isError && !liveTail ? (
          <p className="px-3 py-4 text-sm text-rose-300">
            failed to load logs: {String(recent.error?.message || 'unknown')}
          </p>
        ) : null}
        {count === 0 ? (
          <p className="px-3 py-6 text-center text-sm text-[var(--cos-muted)]">
            no log events match the current filter. write one via{' '}
            <code>cos_log</code> / <code>cos_say</code> to populate the sink.
          </p>
        ) : (
          <table className="w-full table-fixed border-collapse text-left">
            <thead className="bg-[var(--cos-grain)] text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">
              <tr>
                <th className="w-[88px] px-3 py-2">time</th>
                <th className="w-[68px] px-3 py-2">level</th>
                <th className="w-[200px] px-3 py-2">scope</th>
                <th className="px-3 py-2">message</th>
                <th className="w-[260px] px-3 py-2">extras</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event, idx) => (
                <tr
                  key={`${event.ts}-${idx}`}
                  className="border-t border-[var(--cos-border)]/40 align-top text-xs"
                >
                  <td className="px-3 py-1.5 font-mono text-[11px] text-[var(--cos-muted)]">
                    {shortTime(event.ts)}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-[11px]">
                    <span
                      className="rounded px-1.5 py-0.5 font-semibold"
                      style={{
                        color: LEVEL_COLORS[event.lvl] ?? 'inherit',
                        background: `${LEVEL_COLORS[event.lvl] ?? '#888'}22`,
                      }}
                    >
                      {event.lvl}
                    </span>
                  </td>
                  <td className="truncate px-3 py-1.5 font-mono text-[11px] text-[var(--cos-text)]" title={event.scope}>
                    {event.scope}
                  </td>
                  <td className="break-words px-3 py-1.5 text-[var(--cos-text)]">
                    {event.msg}
                  </td>
                  <td className="px-3 py-1.5 align-top">
                    <ExtrasCell event={event} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </PageShell>
  );
}
