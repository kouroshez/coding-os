import { useEffect, useMemo, useRef, useState } from 'react';
import { useApiGet } from '@/lib/hooks';
import { resolveApiUrl } from '@/lib/api-client';

export interface HookEvent {
  iso_ts: string;
  hook: string;
  action: string;
  agent: string;
  session_id: string;
  task: string;
  extras?: Record<string, string>;
}

interface RecentPayload {
  events: HookEvent[];
  count: number;
  log_path: string;
  log_size_bytes: number;
}

const MAX_EVENTS = 200;

const ACTION_PALETTE: Record<string, string> = {
  fire: '#5aa8ff',
  block: '#ef4444',
  warn: '#fbbf24',
  skip: '#9ea4ae',
  'skip-not-replace': '#9ea4ae',
  pass: '#16a34a',
  'stale-gate': '#fbbf24',
};

function relTime(iso: string): string {
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return '';
  const diff = (Date.now() - ms) / 1000;
  if (diff < 1) return 'now';
  if (diff < 60) return `${Math.floor(diff)}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

export default function HookStream() {
  const seed = useApiGet<RecentPayload>(
    ['hooks-recent-seed'],
    '/api/hooks/recent',
    { limit: 100 },
    // No polling — SSE drives updates after the seed.
  );
  const [events, setEvents] = useState<HookEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [filterAgent, setFilterAgent] = useState<string>('all');
  const [filterAction, setFilterAction] = useState<string>('all');
  const [filterText, setFilterText] = useState('');
  const [paused, setPaused] = useState(false);
  const [recentFlash, setRecentFlash] = useState<string | null>(null);
  const flashTimerRef = useRef<number | null>(null);

  // Hydrate the list once from /recent on first load.
  useEffect(() => {
    if (seed.data?.events && events.length === 0) {
      setEvents(seed.data.events);
    }
  }, [seed.data]); // eslint-disable-line react-hooks/exhaustive-deps

  // Live SSE — prepend new events; clamp the list at MAX_EVENTS.
  useEffect(() => {
    const es = new EventSource(resolveApiUrl('/api/hooks/stream'));
    es.addEventListener('connected', () => setConnected(true));
    es.addEventListener('heartbeat', () => setConnected(true));
    es.addEventListener('hook', (ev) => {
      try {
        const payload = JSON.parse((ev as MessageEvent).data) as HookEvent;
        if (paused) return;
        setEvents((cur) => [payload, ...cur].slice(0, MAX_EVENTS));
        setRecentFlash(`${payload.hook}-${payload.iso_ts}`);
        if (flashTimerRef.current) window.clearTimeout(flashTimerRef.current);
        flashTimerRef.current = window.setTimeout(() => setRecentFlash(null), 800);
      } catch {
        // Malformed payload — ignore one event.
      }
    });
    es.onerror = () => setConnected(false);
    return () => {
      es.close();
      if (flashTimerRef.current) window.clearTimeout(flashTimerRef.current);
    };
  }, [paused]);

  const agents = useMemo(() => {
    const s = new Set(events.map((e) => e.agent));
    return Array.from(s).sort();
  }, [events]);
  const actions = useMemo(() => {
    const s = new Set(events.map((e) => e.action));
    return Array.from(s).sort();
  }, [events]);

  const filtered = useMemo(() => {
    const q = filterText.trim().toLowerCase();
    return events.filter((e) => {
      if (filterAgent !== 'all' && e.agent !== filterAgent) return false;
      if (filterAction !== 'all' && e.action !== filterAction) return false;
      if (q && !`${e.hook} ${e.session_id} ${e.task}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [events, filterAgent, filterAction, filterText]);

  // Per-hook histogram (top 8 firing hooks).
  const histo = useMemo(() => {
    const h: Record<string, number> = {};
    for (const e of events) h[e.hook] = (h[e.hook] ?? 0) + 1;
    return Object.entries(h)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8);
  }, [events]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="border-b border-[var(--cos-border)] bg-[var(--cos-panel)] px-3 py-2">
        <div className="flex items-center gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
            Hook stream
          </h2>
          <span
            className={[
              'inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-wider',
              connected
                ? 'border-emerald-500/50 bg-emerald-500/10 text-emerald-300'
                : 'border-[var(--cos-border)] text-[var(--cos-muted)]',
            ].join(' ')}
          >
            <span
              aria-hidden
              className={['inline-block h-1.5 w-1.5 rounded-full', connected ? 'animate-pulse' : ''].join(' ')}
              style={{ background: connected ? '#16a34a' : '#6b7280' }}
            />
            {connected ? 'live' : 'idle'}
          </span>
          <span className="text-[10px] text-[var(--cos-muted)]">
            {filtered.length} / {events.length}
          </span>
          <button
            type="button"
            onClick={() => setPaused((v) => !v)}
            className={[
              'ml-auto rounded border px-2 py-0.5 text-[10px] transition-colors',
              paused
                ? 'border-amber-500/50 bg-amber-500/10 text-amber-300'
                : 'border-[var(--cos-border)] text-[var(--cos-muted)] hover:border-[var(--cos-accent)]',
            ].join(' ')}
          >
            {paused ? 'paused — click to resume' : 'pause'}
          </button>
          <button
            type="button"
            onClick={() => setEvents([])}
            className="rounded border border-[var(--cos-border)] px-2 py-0.5 text-[10px] text-[var(--cos-muted)] hover:border-[var(--cos-accent)]"
          >
            clear
          </button>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <FilterSelect label="agent" value={filterAgent} options={['all', ...agents]} onChange={setFilterAgent} />
          <FilterSelect
            label="action"
            value={filterAction}
            options={['all', ...actions]}
            onChange={setFilterAction}
            colorMap={ACTION_PALETTE}
          />
          <input
            type="search"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            placeholder="filter by hook / session / task"
            className="flex-1 min-w-[160px] rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1 text-[11px]"
          />
        </div>
        {histo.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1 text-[9px]">
            {histo.map(([name, count]) => (
              <span
                key={name}
                className="rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-1.5 py-0.5 font-mono text-[var(--cos-muted)]"
              >
                {name}
                <span className="ml-1 text-[var(--cos-text)]">{count}</span>
              </span>
            ))}
          </div>
        )}
      </header>

      <ol className="flex-1 overflow-auto p-2 cos-scroll">
        {filtered.length === 0 && (
          <li className="p-4 text-center text-xs text-[var(--cos-muted)]">
            no hook events match filter — fire a tool to see live output here.
          </li>
        )}
        {filtered.map((e) => {
          const key = `${e.iso_ts}-${e.hook}-${e.session_id}`;
          const flash = recentFlash === key;
          const color = ACTION_PALETTE[e.action] ?? '#9ea4ae';
          return (
            <li
              key={key}
              className={[
                'mb-1 flex items-center gap-2 rounded border px-2 py-1 text-[11px] transition-colors',
                flash
                  ? 'border-[var(--cos-accent)] bg-[var(--cos-accent)]/8'
                  : 'border-[var(--cos-border)] bg-[var(--cos-panel)]',
              ].join(' ')}
            >
              <span
                aria-hidden
                className="inline-block h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ background: color }}
              />
              <span className="w-12 shrink-0 text-[10px] text-[var(--cos-faint)]">{relTime(e.iso_ts)}</span>
              <span className="w-10 shrink-0 text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">
                {e.action}
              </span>
              <span className="font-mono font-semibold text-[var(--cos-text)]">{e.hook}</span>
              <span className="text-[10px] text-[var(--cos-muted)]">{e.agent}</span>
              {e.task && e.task !== 'none' && (
                <span className="ml-auto truncate font-mono text-[10px] text-[var(--cos-faint)]" title={e.task}>
                  {e.task}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
  colorMap,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
  colorMap?: Record<string, string>;
}) {
  return (
    <label className="flex items-center gap-1 text-[10px] text-[var(--cos-muted)]">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-1 py-0.5 text-[11px] text-[var(--cos-text)]"
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {colorMap && colorMap[o] ? `● ${o}` : o}
          </option>
        ))}
      </select>
    </label>
  );
}
