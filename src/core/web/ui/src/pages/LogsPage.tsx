import { useEffect, useMemo, useRef, useState } from 'react';
import { useApiGet } from '@/lib/hooks';
import { resolveApiUrl } from '@/lib/api-client';
import { acquireEventSource, type SharedEventSource } from '@/lib/shared-event-source';
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

// Backend stamps log timestamps in UTC (…Z, datetime.now(timezone.utc)). Render
// in the VIEWER's local timezone via new Date()+toLocaleTimeString — string-slicing
// the ISO showed the raw UTC time-of-day, so an EDT viewer saw 16:54:16 for a
// 12:54:16 event (TASK-262). Falls back to the raw slice for malformed input.
export function shortTime(iso: string): string {
  if (!iso) return iso;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.length >= 19 ? iso.slice(11, 19) : iso;
  return d.toLocaleTimeString(undefined, { hour12: false });
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

interface GroupedEvent {
  event: LogEvent;
  count: number;
  allEvents: LogEvent[];
}

function groupConsecutiveEvents(events: LogEvent[]): GroupedEvent[] {
  const grouped: GroupedEvent[] = [];
  for (const e of events) {
    if (grouped.length > 0) {
      const lastGroup = grouped[grouped.length - 1];
      if (lastGroup.event.scope === e.scope && lastGroup.event.msg === e.msg) {
        lastGroup.count += 1;
        lastGroup.allEvents.push(e);
        continue;
      }
    }
    grouped.push({
      event: e,
      count: 1,
      allEvents: [e],
    });
  }
  return grouped;
}

export default function LogsPage() {
  const [level, setLevel] = useState<LevelFloor>('debug');
  const [scope, setScope] = useState('');
  const [search, setSearch] = useState('');
  const [since, setSince] = useState('');
  const [limit, setLimit] = useState(200);
  const [liveTail, setLiveTail] = useState(false);
  const [liveEvents, setLiveEvents] = useState<LogEvent[]>([]);
  const [expandedGroups, setExpandedGroups] = useState<Record<number, boolean>>({});
  const sourceRef = useRef<SharedEventSource | null>(null);

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
      sourceRef.current?.release();
      sourceRef.current = null;
      return;
    }
    setLiveEvents([]);
    const streamParams: Record<string, unknown> = { level };
    if (scope) streamParams.scope = scope;
    if (search) streamParams.search = search;
    const url = resolveApiUrl('/api/logs/stream', streamParams);
    const shared = acquireEventSource(url);
    const source = shared.source;
    sourceRef.current = shared;
    const onLog = (ev: Event) => {
      try {
        const parsed: LogEvent = JSON.parse((ev as MessageEvent).data);
        setLiveEvents((prev) => {
          const next = [...prev, parsed];
          return next.length > TAIL_CAP ? next.slice(-TAIL_CAP) : next;
        });
      } catch {
        // ignore malformed payload
      }
    };
    source.addEventListener('log', onLog);
    return () => {
      source.removeEventListener('log', onLog);
      shared.release();
      sourceRef.current = null;
    };
  }, [liveTail, level, scope, search]);

  // Reset expanded states when log data changes
  useEffect(() => {
    setExpandedGroups({});
  }, [liveTail, level, scope, search, since, limit]);

  const toggleGroup = (idx: number) => {
    setExpandedGroups((prev) => ({ ...prev, [idx]: !prev[idx] }));
  };

  const events = liveTail ? liveEvents : recent.data?.events ?? [];
  const count = events.length;
  const logPath = recent.data?.log_path ?? '';

  return (
    <PageShell>
      <PageHeader
        eyebrow={<StatusPill label={liveTail ? 'logs · live tail' : 'logs · tail'} dotColor={liveTail ? 'bg-[var(--cos-ok-tint)]' : 'bg-[var(--cos-warn-tint)]'} />}
        title="Logs"
        subtitle="Structured agent + server activity from .cos.log.jsonl — filter by level, scope (glob), substring, or relative window."
      />

      <section className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-6 bg-[var(--cos-panel)]/40 backdrop-blur-md border border-[var(--cos-border)]/30 rounded-2xl p-4">
        <label className="flex flex-col gap-1 text-[10px] uppercase tracking-wider text-[var(--cos-muted)] font-mono">
          level floor
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value as LevelFloor)}
            className="rounded-xl border border-[var(--cos-border)]/60 bg-[var(--cos-panel)] px-3 py-1.5 font-mono text-xs text-[var(--cos-text)] focus:border-[var(--cos-accent)] focus:outline-none"
          >
            {LEVELS.map((lv) => (
              <option key={lv} value={lv}>{lv}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[10px] uppercase tracking-wider text-[var(--cos-muted)] font-mono">
          scope (glob)
          <input
            value={scope}
            onChange={(e) => setScope(e.target.value)}
            placeholder="hook.* / core.*"
            className="rounded-xl border border-[var(--cos-border)]/60 bg-[var(--cos-panel)] px-3 py-1.5 font-mono text-xs text-[var(--cos-text)] placeholder:text-[var(--cos-muted)] focus:border-[var(--cos-accent)] focus:outline-none"
          />
        </label>
        <label className="flex flex-col gap-1 text-[10px] uppercase tracking-wider text-[var(--cos-muted)] font-mono">
          msg substring
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="match…"
            className="rounded-xl border border-[var(--cos-border)]/60 bg-[var(--cos-panel)] px-3 py-1.5 font-mono text-xs text-[var(--cos-text)] placeholder:text-[var(--cos-muted)] focus:border-[var(--cos-accent)] focus:outline-none"
          />
        </label>
        <label className="flex flex-col gap-1 text-[10px] uppercase tracking-wider text-[var(--cos-muted)] font-mono">
          since (duration)
          <input
            value={since}
            onChange={(e) => setSince(e.target.value)}
            placeholder="10m / 1h"
            disabled={liveTail}
            className="rounded-xl border border-[var(--cos-border)]/60 bg-[var(--cos-panel)] px-3 py-1.5 font-mono text-xs text-[var(--cos-text)] placeholder:text-[var(--cos-muted)] disabled:opacity-50 focus:border-[var(--cos-accent)] focus:outline-none"
          />
        </label>
        <label className="flex flex-col gap-1 text-[10px] uppercase tracking-wider text-[var(--cos-muted)] font-mono">
          limit
          <input
            type="number"
            min={1}
            max={2000}
            value={limit}
            disabled={liveTail}
            onChange={(e) => setLimit(Math.max(1, Math.min(2000, Number(e.target.value) || 1)))}
            className="rounded-xl border border-[var(--cos-border)]/60 bg-[var(--cos-panel)] px-3 py-1.5 font-mono text-xs text-[var(--cos-text)] disabled:opacity-50 focus:border-[var(--cos-accent)] focus:outline-none"
          />
        </label>
        <div className="flex items-end">
          <button
            type="button"
            onClick={() => setLiveTail((v) => !v)}
            className={[
              'h-[34px] w-full rounded-xl font-mono text-xs font-semibold transition-all duration-150',
              liveTail
                ? 'bg-[var(--cos-ok-tint)] text-[var(--cos-ok)] border border-[var(--cos-ok)] shadow-md  hover:bg-[var(--cos-ok-tint)]'
                : 'bg-[var(--cos-panel)] text-[var(--cos-text)] border border-[var(--cos-border)]/70 hover:border-[var(--cos-accent)] hover:text-[var(--cos-accent)] hover:-translate-y-px active:translate-y-0',
            ].join(' ')}
          >
            {liveTail ? 'live · stop' : 'tail live'}
          </button>
        </div>
      </section>

      <section className="mt-4 rounded border border-[var(--cos-border)] bg-[var(--cos-panel)]">
        <header className="flex items-center justify-between border-b border-[var(--cos-border)] px-3 py-2 font-mono text-[11px] text-[var(--cos-muted)]">
          <span>{count} event{count === 1 ? '' : 's'}{liveTail ? ' · streaming' : ''}</span>
          <span className="truncate" title={logPath}>{logPath || '.coding-os/.cos.log.jsonl'}</span>
        </header>
        {recent.isError && !liveTail ? (
          <p className="px-3 py-4 text-sm text-[var(--cos-err)]">
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
              {(() => {
                const grouped = groupConsecutiveEvents(events);
                return grouped.flatMap((group, idx) => {
                  const isExpanded = expandedGroups[idx];
                  const rows = [];
                  rows.push(
                    <tr
                      key={`${group.event.ts}-${idx}-primary`}
                      className="border-t border-[var(--cos-border)]/40 align-top text-xs hover:bg-[var(--cos-panel)]/40"
                    >
                      <td className="px-3 py-2 font-mono text-[11px] text-[var(--cos-muted)]">
                        {shortTime(group.event.ts)}
                      </td>
                      <td className="px-3 py-2 font-mono text-[11px]">
                        <span
                          className="rounded-lg px-2 py-0.5 font-mono text-[10px] font-semibold"
                          style={{
                            color: LEVEL_COLORS[group.event.lvl] ?? 'inherit',
                            background: `${LEVEL_COLORS[group.event.lvl] ?? '#888'}18`,
                          }}
                        >
                          {group.event.lvl}
                        </span>
                      </td>
                      <td className="truncate px-3 py-2 font-mono text-[11px] text-[var(--cos-muted)]" title={group.event.scope}>
                        {group.event.scope}
                      </td>
                      <td className="break-words px-3 py-2 text-[var(--cos-text)]">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium">{group.event.msg}</span>
                          {group.count > 1 && (
                            <button
                              type="button"
                              onClick={() => toggleGroup(idx)}
                              className="inline-flex items-center cursor-pointer rounded-full bg-[var(--cos-accent)]/10 border border-[var(--cos-accent)]/20 px-2 py-0.5 text-[9px] font-mono font-semibold text-[var(--cos-accent)] hover:bg-[var(--cos-accent)]/20 transition-all select-none focus:outline-none"
                            >
                              {isExpanded ? '▼ hide repeats' : `▶ +${group.count - 1} repeated`}
                            </button>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2 align-top">
                        <ExtrasCell event={group.event} />
                      </td>
                    </tr>
                  );

                  if (isExpanded && group.count > 1) {
                    group.allEvents.slice(1).forEach((subEv, subIdx) => {
                      rows.push(
                        <tr
                          key={`${subEv.ts}-${idx}-sub-${subIdx}`}
                          className="bg-[var(--cos-bg)]/20 border-t border-[var(--cos-border)]/20 align-top text-xs opacity-80 hover:opacity-100"
                        >
                          <td className="pl-6 pr-3 py-1.5 font-mono text-[11px] text-[var(--cos-muted)]">
                            ↳ {shortTime(subEv.ts)}
                          </td>
                          <td className="px-3 py-1.5 font-mono text-[11px] opacity-60">
                            {subEv.lvl}
                          </td>
                          <td className="truncate px-3 py-1.5 font-mono text-[11px] text-[var(--cos-muted)]" title={subEv.scope}>
                            {subEv.scope}
                          </td>
                          <td className="break-words px-3 py-1.5 text-[var(--cos-muted)] italic">
                            {subEv.msg}
                          </td>
                          <td className="px-3 py-1.5 align-top">
                            <ExtrasCell event={subEv} />
                          </td>
                        </tr>
                      );
                    });
                  }

                  return rows;
                });
              })()}
            </tbody>
          </table>
        )}
      </section>
    </PageShell>
  );
}
