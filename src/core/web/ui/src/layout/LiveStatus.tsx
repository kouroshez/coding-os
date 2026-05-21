import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useApiGet } from '@/lib/hooks';
import { resolveApiUrl } from '@/lib/api-client';
import { useScopedLink } from '@/lib/use-scoped-link';

interface AgentRuntime {
  agent: string;
  session_id?: string | null;
  task?: string | null;
  skill_active?: string | null;
  model?: string | null;
  gate?: string | null;
}

interface PresencePayload {
  project_root: string;
  state_dir: string;
  agents: AgentRuntime[];
  agent_states: Record<string, string>;
  last_hook: {
    iso_ts: string;
    hook: string;
    action: string;
    agent: string;
    session_id: string;
    task: string;
  } | null;
  current_chat_uuid: string | null;
}

const STATE_PALETTE: Record<string, { dot: string; label: string; pulse: boolean }> = {
  active: { dot: '#16a34a', label: 'active', pulse: true },
  working: { dot: '#16a34a', label: 'working', pulse: true },
  present: { dot: '#fbbf24', label: 'present', pulse: false },
  idle: { dot: '#fbbf24', label: 'idle', pulse: false },
  offline: { dot: '#6b7280', label: 'offline', pulse: false },
};

function relTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return '';
  const diff = (Date.now() - ms) / 1000;
  if (diff < 5) return 'just now';
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function LiveStatus() {
  const { scopedLink } = useScopedLink();
  const { data } = useApiGet<PresencePayload>(
    ['presence-now'],
    '/api/presence/now',
    undefined,
    { refetchIntervalMs: 4000 },
  );
  const [open, setOpen] = useState(false);
  const [liveHook, setLiveHook] = useState<PresencePayload['last_hook']>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  // Subscribe to the hook stream for the freshest "X firing now" tick —
  // independent of the 4s polling interval. Reconnect on URL changes
  // (per-project scope) via the resolveApiUrl indirection.
  useEffect(() => {
    const url = resolveApiUrl('/api/hooks/stream');
    const es = new EventSource(url);
    es.addEventListener('hook', (ev) => {
      try {
        const payload = JSON.parse((ev as MessageEvent).data);
        setLiveHook(payload);
      } catch {
        // Malformed payload — skip silently; next event will recover.
      }
    });
    es.onerror = () => {
      // Browser auto-reconnects with backoff; nothing for us to do.
    };
    return () => es.close();
  }, []);

  // Click-outside to close popover.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      const target = e.target as Node;
      if (!popRef.current?.contains(target) && !btnRef.current?.contains(target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const states = data?.agent_states ?? {};
  // Order: agents currently doing work (active/working) first, then present, then human.
  const liveAgents = Object.entries(states)
    .filter(([id, s]) => s !== 'offline' && id !== 'human')
    .sort((a, b) => {
      const rank = (s: string) => (s === 'active' || s === 'working' ? 0 : s === 'present' ? 1 : 2);
      return rank(a[1]) - rank(b[1]);
    });
  const primaryAgent = liveAgents[0]?.[0] ?? null;
  const primarySnap = data?.agents.find((a) => a.agent === primaryAgent) ?? null;

  const lastHook = liveHook ?? data?.last_hook ?? null;

  const sessionLabel = primarySnap?.session_id
    ? primarySnap.session_id.split('-').slice(2).join('-').slice(0, 12)
    : 'no session';

  return (
    <div className="relative">
      <button
        ref={btnRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="dialog"
        aria-expanded={open}
        title={
          liveAgents.length === 0
            ? 'no live agent'
            : liveAgents.map(([id, s]) => `${id}: ${s}`).join(' · ')
        }
        className="flex items-center gap-2 rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1 font-mono text-[11px] hover:border-[var(--cos-accent)]"
      >
        {liveAgents.length === 0 ? (
          <span
            aria-hidden
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: STATE_PALETTE.offline.dot }}
          />
        ) : (
          <span className="flex items-center gap-0.5">
            {liveAgents.map(([id, s]) => {
              const pal = STATE_PALETTE[s] ?? STATE_PALETTE.offline;
              return (
                <span
                  key={id}
                  aria-hidden
                  className={['inline-block h-2 w-2 rounded-full', pal.pulse ? 'animate-pulse' : ''].join(' ')}
                  style={{ background: pal.dot }}
                  title={`${id}: ${s}`}
                />
              );
            })}
          </span>
        )}
        {liveAgents.length === 0 ? (
          <span className="text-[var(--cos-muted)]">idle</span>
        ) : liveAgents.length === 1 ? (
          <span className="text-[var(--cos-text)]">{primaryAgent}</span>
        ) : (
          <span className="text-[var(--cos-text)]">
            {primaryAgent}
            <span className="text-[var(--cos-muted)]"> +{liveAgents.length - 1}</span>
          </span>
        )}
        {primarySnap?.session_id && (
          <>
            <span className="text-[var(--cos-muted)]">·</span>
            <span className="text-[var(--cos-muted)]">{sessionLabel}</span>
          </>
        )}
        {lastHook && (
          <>
            <span className="text-[var(--cos-muted)]">·</span>
            <span className="text-[var(--cos-faint)]">{lastHook.hook}</span>
            <span className="text-[var(--cos-faint)]">{relTime(lastHook.iso_ts)}</span>
          </>
        )}
      </button>
      {open && data && (
        <div
          ref={popRef}
          role="dialog"
          className="absolute left-0 top-[calc(100%+4px)] z-50 w-[380px] overflow-hidden rounded-md border border-[var(--cos-border)] bg-[var(--cos-panel)] shadow-lg"
        >
          <header className="border-b border-[var(--cos-border)] px-3 py-2">
            <h2 className="text-[10px] font-semibold uppercase tracking-wider text-[var(--cos-muted)]">
              Live HUD
            </h2>
            <p className="mt-0.5 font-mono text-[10px] text-[var(--cos-faint)]">
              {data.project_root}
            </p>
          </header>

          <div className="border-b border-[var(--cos-border)] px-3 py-2">
            <div className="mb-1 text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">
              agents
            </div>
            <ul className="space-y-1">
              {Object.entries(states).map(([id, st]) => {
                const pal = STATE_PALETTE[st] ?? STATE_PALETTE.offline;
                const snap = data.agents.find((a) => a.agent === id) ?? null;
                return (
                  <li key={id} className="flex items-center gap-2 text-[11px]">
                    <span
                      aria-hidden
                      className={['inline-block h-1.5 w-1.5 rounded-full', pal.pulse ? 'animate-pulse' : ''].join(' ')}
                      style={{ background: pal.dot }}
                    />
                    <span className="font-mono text-[var(--cos-text)]">{id}</span>
                    <span className="text-[var(--cos-muted)]">{pal.label}</span>
                    {snap?.task && (
                      <span className="ml-auto truncate font-mono text-[10px] text-[var(--cos-faint)]">
                        {snap.task}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>

          {liveAgents.map(([agentId]) => {
            const snap = data.agents.find((a) => a.agent === agentId);
            if (!snap) return null;
            return (
              <div key={agentId} className="border-b border-[var(--cos-border)] px-3 py-2 text-[11px]">
                <div className="mb-1 flex items-center gap-2 text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">
                  <span>{snap.agent} runtime</span>
                </div>
                <Row k="session" v={snap.session_id ?? '—'} mono />
                <Row k="task" v={snap.task ?? '—'} />
                <Row k="skill" v={snap.skill_active ?? '—'} />
                <Row k="model" v={snap.model ?? '—'} mono />
                <Row k="gate" v={snap.gate ?? '—'} />
              </div>
            );
          })}

          {lastHook && (
            <div className="border-b border-[var(--cos-border)] px-3 py-2 text-[11px]">
              <div className="mb-1 text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">
                last hook fire
              </div>
              <Row k="hook" v={`${lastHook.hook} · ${lastHook.action}`} />
              <Row k="when" v={`${lastHook.iso_ts} (${relTime(lastHook.iso_ts)})`} />
              <Row k="agent" v={lastHook.agent} />
            </div>
          )}

          <div className="flex items-center justify-between px-3 py-2 text-[10px]">
            <Link
              to={scopedLink('cognition', '?view=live')}
              onClick={() => setOpen(false)}
              className="text-[var(--cos-accent)] hover:underline"
            >
              live hook stream →
            </Link>
            {data.current_chat_uuid && (
              <Link
                to={scopedLink('cognition', `${encodeURIComponent(data.current_chat_uuid)}?view=chat`)}
                onClick={() => setOpen(false)}
                className="text-[var(--cos-accent)] hover:underline"
              >
                open current chat →
              </Link>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline gap-2 py-0.5">
      <span className="w-14 shrink-0 text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">
        {k}
      </span>
      <span
        className={[
          'min-w-0 flex-1 truncate text-[var(--cos-text)]',
          mono ? 'font-mono text-[10px]' : 'text-[11px]',
        ].join(' ')}
      >
        {v}
      </span>
    </div>
  );
}
