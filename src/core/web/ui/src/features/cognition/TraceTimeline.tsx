import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useApiGet } from '@/lib/hooks';
import { resolveApiUrl } from '@/lib/api-client';
import { acquireEventSource } from '@/lib/shared-event-source';
import { useScopedLink } from '@/lib/use-scoped-link';

interface TraceEvent {
  kind?: string;
  ts?: number;
  node?: string;
  role?: string | null;
  phase?: string | null;
  // The producer (thinking_os/tracing.py:112) nests summary/formula_id/
  // status/latency under `data`; only kind/ts/node/role/phase are top-level.
  data?: Record<string, unknown> | null;
  raw?: string;
  [key: string]: unknown;
}

interface SessionMeta {
  agent?: string;
  session_id?: string;
  sdk_uuid?: string | null;
  pid?: number;
  started_at?: number;
  last_prompt_at?: number;
  last_tool_at?: number;
  last_stop_at?: number | null;
  ended_at?: number | null;
}

interface TracePayload {
  session_id: string;
  agent?: string | null;
  events: TraceEvent[];
  count: number;
  session?: SessionMeta | null;
  has_trace?: boolean;
  source?: 'trace+session' | 'trace-only' | 'session-only';
}

// Keys MUST match the kinds thinking_os/tracing.py actually emits.
const EVENT_COLORS: Record<string, string> = {
  classify: '#e0a227',
  analyze_start: '#e0a227',
  analyze_done: '#e0a227',
  compose_done: '#7c82f2',
  dispatch_started: '#3fb950',
  dispatch_completed: '#2e9e6e',
  parallel_dispatch: '#3fb950',
  role_dispatch: '#4c8dff',
  role_output_recorded: '#4c8dff',
  supervise_action: '#4c8dff',
  backtrack: '#f2576b',
  anti_paralysis_warn: '#f0a850',
  task_done: '#2e9e6e',
  error: '#f2576b',
};

function eventColor(kind: string | undefined): string {
  if (!kind) return '#6c7480';
  return EVENT_COLORS[kind] ?? '#6c7480';
}

function eventKey(e: TraceEvent, i: number): string {
  return `${i}-${e.kind ?? 'event'}-${e.ts ?? ''}`;
}

// Plain-language labels for cognition event kinds so a non-developer reads
// "what the agent did" instead of OTEL-style internals.
const KIND_LABEL: Record<string, string> = {
  classify: 'Classified the request',
  analyze_start: 'Started analysing the task',
  analyze_done: 'Finished analysing the task',
  compose_done: 'Composed the role chain',
  dispatch_started: 'Dispatched a sub-agent',
  dispatch_completed: 'Sub-agent finished',
  role_dispatch: 'Ran a role',
  role_output_recorded: 'Recorded role evidence',
  supervise_action: 'Supervised a step',
  parallel_dispatch: 'Ran sub-agents in parallel',
  backtrack: 'Reconsidered (backtrack)',
  anti_paralysis_warn: 'Anti-paralysis nudge',
  task_done: 'Marked the task done',
};

function humanLabel(kind: string): string {
  return KIND_LABEL[kind] ?? kind.replace(/_/g, ' ');
}

function fmtTime(ts?: number): string {
  if (!ts) return '';
  return new Date(ts * 1000).toLocaleTimeString();
}

function humanDetail(e: TraceEvent): string {
  const d: Record<string, unknown> = e.data ?? {};
  if (d.summary) return String(d.summary);
  const bits: string[] = [];
  if (e.role) bits.push(`role: ${String(e.role)}`);
  if (e.phase) bits.push(`phase: ${String(e.phase)}`);
  if (d.formula_id != null) bits.push(`formula: ${String(d.formula_id)}`);
  if (d.status != null) bits.push(`status: ${String(d.status)}`);
  if (d.latency_ms != null) bits.push(`${String(d.latency_ms)}ms`);
  return bits.join(' · ') || 'no further detail recorded';
}

// Map the producer's flowchart node (tracing.py FLOWCHART_NODES) to a human
// phase so the timeline reads Setup -> Plan -> Execute -> Verify -> Close.
const PHASE_BY_NODE: Record<string, string> = {
  'n-sinit': 'setup',
  'n-gate': 'setup',
  'n-analyzer': 'plan',
  'n-router': 'plan',
  'n-supervisor': 'execute',
  'n-impl': 'execute',
  'n-ambi': 'verify',
  'n-trace': 'verify',
  'n-verify': 'verify',
  'n-done': 'close',
  'n-end': 'close',
};
const PHASE_ORDER = ['setup', 'plan', 'execute', 'verify', 'close', 'other'] as const;
const PHASE_LABEL: Record<string, string> = {
  setup: 'Setup',
  plan: 'Plan',
  execute: 'Execute',
  verify: 'Verify',
  close: 'Close',
  other: 'Other',
};

function phaseOf(e: TraceEvent): string {
  return PHASE_BY_NODE[e.node ?? ''] ?? 'other';
}

export default function TraceTimeline({ sessionId }: { sessionId: string }) {
  const { scopedLink } = useScopedLink();
  const { data, isLoading, error } = useApiGet<TracePayload>(
    ['cognition-trace', sessionId],
    `/api/cognition/trace/${encodeURIComponent(sessionId)}`,
    undefined,
    { refetchIntervalMs: 5000 },
  );
  const [expanded, setExpanded] = useState<string | null>(null);
  const [kindFilter, setKindFilter] = useState<string>('all');
  // Default to the readable summary; raw cognition internals behind a toggle.
  const [mode, setMode] = useState<'summary' | 'raw'>('summary');
  const [liveEvents, setLiveEvents] = useState<TraceEvent[]>([]);
  const [streamError, setStreamError] = useState<string | null>(null);

  // Live tail — the dispatch/cognition trace SSE route appends events the
  // instant they land, on top of the initial fetch, so a running dispatch is
  // watchable in real time. A mid-stream backend error surfaces via streamError
  // instead of silently freezing the tail.
  useEffect(() => {
    setLiveEvents([]);
    setStreamError(null);
    const shared = acquireEventSource(
      resolveApiUrl(`/api/cognition/trace/${encodeURIComponent(sessionId)}/stream`),
    );
    const es = shared.source;
    const onTrace = (ev: Event) => {
      try {
        setLiveEvents((cur) => [...cur, JSON.parse((ev as MessageEvent).data) as TraceEvent]);
        // A trace event arriving means the tail recovered — clear any prior
        // stream error so the banner doesn't stick after a transient blip.
        setStreamError(null);
      } catch {
        // Malformed line — skip one event.
      }
    };
    const onStreamError = (ev: Event) => {
      // Only surface the server's `event: error` frame (it carries data); a
      // native reconnect blip (no data) is transient and must not false-alarm.
      const data = (ev as MessageEvent).data;
      if (typeof data !== 'string') return;
      try {
        setStreamError((JSON.parse(data)?.message as string) ?? 'trace stream error');
      } catch {
        setStreamError('trace stream error');
      }
    };
    es.addEventListener('trace', onTrace);
    es.addEventListener('error', onStreamError);
    return () => {
      es.removeEventListener('trace', onTrace);
      es.removeEventListener('error', onStreamError);
      shared.release();
    };
  }, [sessionId]);

  const events = useMemo(() => {
    const base = data?.events ?? [];
    const seen = new Set<string>();
    const merged: TraceEvent[] = [];
    for (const e of [...base, ...liveEvents]) {
      // Dedup by span_id (always present from tracing.py); span_id-less lines
      // (malformed/foreign) dedup on their full content, so an identical event
      // replayed by the SSE tail collapses while two distinct events don't.
      const key = typeof e.span_id === 'string' ? e.span_id : JSON.stringify(e);
      if (seen.has(key)) continue;
      seen.add(key);
      merged.push(e);
    }
    return merged;
  }, [data?.events, liveEvents]);
  const kinds = useMemo(() => {
    const s = new Set<string>();
    for (const e of events) s.add(e.kind ?? 'event');
    return Array.from(s).sort();
  }, [events]);
  const histogram = useMemo(() => {
    const h: Record<string, number> = {};
    for (const e of events) {
      const k = e.kind ?? 'event';
      h[k] = (h[k] ?? 0) + 1;
    }
    return h;
  }, [events]);
  const filtered = useMemo(
    () => (kindFilter === 'all' ? events : events.filter((e) => (e.kind ?? 'event') === kindFilter)),
    [events, kindFilter],
  );
  // Summary view groups events into the 5 cognitive phases so a human scans
  // the story instead of a flat wall; raw view stays chronological.
  const grouped = useMemo(() => {
    const buckets: Record<string, { e: TraceEvent; idx: number }[]> = {};
    filtered.forEach((e, idx) => {
      const p = phaseOf(e);
      (buckets[p] ??= []).push({ e, idx });
    });
    return PHASE_ORDER.filter((p) => buckets[p]?.length).map((p) => ({ phase: p, items: buckets[p] }));
  }, [filtered]);
  const toggleExpand = (key: string) => setExpanded((cur) => (cur === key ? null : key));

  if (isLoading) return <p className="p-4 text-sm text-[var(--cos-muted)]">loading events…</p>;
  if (error)
    return (
      <p role="alert" className="p-4 text-sm text-[var(--cos-err)]">
        {error.message}
      </p>
    );
  if (!data)
    return <p className="p-4 text-sm text-[var(--cos-muted)]">no data.</p>;
  if (events.length === 0)
    return <SessionOnlyView sessionId={sessionId} session={data.session ?? null} agent={data.agent ?? null} />;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="border-b border-[var(--cos-border)] px-4 py-2">
        <div className="flex items-center gap-2">
          <h2 className="font-mono text-xs font-semibold text-[var(--cos-text)]">{data.session_id}</h2>
          {data.session?.sdk_uuid && (
            <Link
              to={scopedLink('cognition', `${encodeURIComponent(data.session.sdk_uuid)}?view=chat`)}
              className="ml-auto text-[10px] text-[var(--cos-accent)] hover:underline"
              title="see SDK chat transcript for the session that produced these events"
            >
              see chat →
            </Link>
          )}
        </div>
        <p className="mt-0.5 text-[10px] text-[var(--cos-muted)]">
          {events.length} event{events.length === 1 ? '' : 's'}
          {mode === 'raw' ? ` · ${filtered.length} shown` : ''}
        </p>
        {streamError && (
          <p className="mt-0.5 text-[10px] text-[var(--cos-danger,#e5484d)]" role="status">
            ⚠ live tail interrupted: {streamError}
          </p>
        )}
        <div className="mt-1.5 flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              const next = mode === 'summary' ? 'raw' : 'summary';
              setMode(next);
              if (next === 'summary') setKindFilter('all');
            }}
            className="rounded border border-[var(--cos-border)] px-2 py-0.5 text-[10px] text-[var(--cos-muted)] hover:text-[var(--cos-text)]"
          >
            {mode === 'summary' ? 'raw events (dev) →' : '← readable summary'}
          </button>
        </div>
        {mode === 'raw' && (
          <div className="mt-2 flex flex-wrap gap-1">
            <FilterChip label={`all (${events.length})`} active={kindFilter === 'all'} onClick={() => setKindFilter('all')} />
            {kinds.map((k) => (
              <FilterChip
                key={k}
                label={`${k} (${histogram[k]})`}
                active={kindFilter === k}
                onClick={() => setKindFilter(k)}
                color={eventColor(k)}
              />
            ))}
          </div>
        )}
      </header>
      <div className="flex-1 overflow-auto p-3 cos-scroll">
        {mode === 'raw' ? (
          <ol>
            {filtered.map((e, i) => (
              <EventRow key={eventKey(e, i)} e={e} idx={i} mode={mode} expanded={expanded} onToggle={toggleExpand} />
            ))}
          </ol>
        ) : (
          grouped.map(({ phase, items }) => (
            <section key={phase} className="mb-4">
              <h3 className="mb-1.5 flex items-center gap-2 text-[10px] font-semibold tracking-widest text-[var(--cos-muted)] uppercase">
                {PHASE_LABEL[phase]}
                <span className="rounded-full bg-[var(--cos-border)]/40 px-1.5 text-[9px] text-[var(--cos-text)]">
                  {items.length}
                </span>
              </h3>
              <ol className="border-l border-[var(--cos-border)] pl-3">
                {items.map(({ e, idx }) => (
                  <EventRow key={eventKey(e, idx)} e={e} idx={idx} mode={mode} expanded={expanded} onToggle={toggleExpand} />
                ))}
              </ol>
            </section>
          ))
        )}
      </div>
    </div>
  );
}

function EventRow({
  e,
  idx,
  mode,
  expanded,
  onToggle,
}: {
  e: TraceEvent;
  idx: number;
  mode: 'summary' | 'raw';
  expanded: string | null;
  onToggle: (key: string) => void;
}) {
  const kind = e.kind ?? 'event';
  const d: Record<string, unknown> = e.data ?? {};
  const dot = eventColor(kind);
  const key = eventKey(e, idx);
  const open = expanded === key;
  return (
    <li
      className={[
        'mb-2 rounded border bg-[var(--cos-panel)] text-xs transition-colors',
        open ? 'border-[var(--cos-accent)]' : 'border-[var(--cos-border)]',
      ].join(' ')}
    >
      <button
        type="button"
        onClick={() => onToggle(key)}
        className="block w-full px-2 py-1.5 text-left"
        aria-expanded={open}
      >
        <div className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: dot }} aria-hidden />
          <span className="font-semibold">{mode === 'raw' ? kind : humanLabel(kind)}</span>
          {d.formula_id != null && (
            <span className="rounded bg-[var(--cos-border)]/40 px-1 text-[10px] text-[var(--cos-text)]">
              {String(d.formula_id)}
            </span>
          )}
          {e.ts != null && (
            <span className="ml-auto text-[10px] text-[var(--cos-muted)]">{fmtTime(e.ts)}</span>
          )}
        </div>
        {d.summary != null && <p className="mt-1 text-[var(--cos-text)]">{String(d.summary)}</p>}
      </button>
      {open &&
        (mode === 'raw' ? (
          <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words border-t border-[var(--cos-border)] bg-[var(--cos-bg)] p-2 font-mono text-[10px] text-[var(--cos-text)] cos-scroll">
            {JSON.stringify(e, null, 2)}
          </pre>
        ) : (
          <p className="border-t border-[var(--cos-border)] bg-[var(--cos-bg)] p-2 text-[11px] text-[var(--cos-text)]">
            {humanDetail(e)}
          </p>
        ))}
    </li>
  );
}

function FilterChip({
  label,
  active,
  onClick,
  color,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  color?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        'flex items-center gap-1 rounded border px-2 py-0.5 text-[10px] transition-colors',
        active
          ? 'border-[var(--cos-accent)] bg-[var(--cos-accent)]/10 text-[var(--cos-accent)]'
          : 'border-[var(--cos-border)] text-[var(--cos-muted)] hover:border-[var(--cos-accent)]',
      ].join(' ')}
    >
      {color && <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: color }} aria-hidden />}
      {label}
    </button>
  );
}

function SessionOnlyView({
  sessionId,
  session,
  agent,
}: {
  sessionId: string;
  session: SessionMeta | null;
  agent: string | null;
}) {
  const fmt = (epoch?: number | null) => {
    if (!epoch) return '—';
    return new Date(epoch * 1000).toLocaleString();
  };
  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-[var(--cos-border)] px-4 py-2">
        <h2 className="font-mono text-xs font-semibold text-[var(--cos-text)]">{sessionId}</h2>
        <p className="mt-0.5 text-[10px] text-[var(--cos-muted)]">
          {agent ? `${agent} · ` : ''}session-only · no cognition trace recorded yet
        </p>
      </header>
      <div className="flex-1 overflow-auto p-4 cos-scroll">
        {!session ? (
          <p className="text-sm text-[var(--cos-muted)]">no session metadata available.</p>
        ) : (
          <dl className="grid grid-cols-1 gap-1 text-xs text-[var(--cos-text)] sm:grid-cols-2">
            <Row k="agent" v={session.agent ?? agent ?? '—'} />
            <Row k="pid" v={session.pid != null ? String(session.pid) : '—'} />
            <Row k="started" v={fmt(session.started_at)} />
            <Row k="last prompt" v={fmt(session.last_prompt_at)} />
            <Row k="last tool" v={fmt(session.last_tool_at)} />
            <Row k="last stop" v={fmt(session.last_stop_at)} />
            <Row k="ended" v={fmt(session.ended_at)} />
          </dl>
        )}
        <p className="mt-4 rounded border border-[var(--cos-border)] bg-[var(--cos-panel)] p-3 text-[11px] text-[var(--cos-muted)]">
          this tab is scoped to <strong>cognition events</strong> only — they are
          written to <code>.coding-os/{agent ?? '&lt;agent&gt;'}/traces/{sessionId}.jsonl</code>{' '}
          by four MCP tools: <code>cos_analyze_task</code>,{' '}
          <code>cos_compose_chain</code>, <code>cos_supervise_record_output</code>,{' '}
          <code>cos_backtrack_log</code>.
          {' '}an empty list is <strong>normal</strong> for retrieval-only or pure
          edit sessions — file edits, board ops, and graph queries do not seed
          cognition traces by design.
          {' '}for general agent activity see{' '}
          <code>cos hooks-log --follow</code>, the activity log{' '}
          <code>.coding-os/.cos.log</code>, or the upcoming{' '}
          <strong>Logs</strong> tab.
        </p>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-baseline gap-2 rounded border border-[var(--cos-border)] bg-[var(--cos-panel)] px-2 py-1">
      <span className="w-20 shrink-0 text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">
        {k}
      </span>
      <span className="min-w-0 flex-1 truncate font-mono text-[11px]">{v}</span>
    </div>
  );
}
