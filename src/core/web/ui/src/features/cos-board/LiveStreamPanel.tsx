import { AgentPip } from './AgentBadges';
import { EVENT_COLOR, EVENT_LABEL } from './board-shared';
import type { BoardEvent } from './useBoardStream';

export function LiveStreamPanel({
  open,
  onClose,
  events,
  connected,
}: {
  open: boolean;
  onClose: () => void;
  events: BoardEvent[];
  connected: boolean;
}) {
  if (!open) return null;
  return (
    <div
      style={{
        position: 'fixed',
        top: 160,
        right: 14,
        bottom: 60,
        width: 380,
        zIndex: 50,
        background: 'var(--col-bg)',
        border: '1px solid var(--col-border)',
        borderRadius: 6,
        boxShadow: '0 20px 40px -10px rgba(0,0,0,.3)',
        display: 'flex',
        flexDirection: 'column',
        fontFamily: "'JetBrains Mono', monospace",
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 12px',
          borderBottom: '1px solid var(--col-border)',
        }}
      >
        <div
          style={{
            fontFamily: 'inherit',
            fontSize: 14,
            letterSpacing: '.04em',
            color: 'var(--accent)',
          }}
        >
          AGENT STREAM
        </div>
        <span style={{ fontSize: 10, color: 'var(--ink-faint)' }}>
          <span
            style={{
              display: 'inline-block',
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: connected ? 'var(--cos-ok)' : 'var(--cos-err)',
              marginRight: 4,
              animation: connected ? 'pulse 1.5s infinite' : 'none',
            }}
          />
          {connected ? 'sse online' : 'sse offline'}
        </span>
        <button
          type="button"
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--ink-faint)',
            cursor: 'pointer',
            fontSize: 16,
            lineHeight: 1,
            padding: 0,
          }}
        >
          ×
        </button>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '6px 4px' }}>
        {events.length === 0 && (
          <div
            style={{
              padding: '24px 14px',
              fontSize: 11,
              color: 'var(--ink-faint)',
              textAlign: 'center',
              lineHeight: 1.5,
            }}
          >
            waiting for events…
            <br />
            (drag a card or let agents touch docs/tasks/*.md)
          </div>
        )}
        {events.map((ev) => {
          const color = EVENT_COLOR[ev.kind] || 'var(--ink-soft)';
          const label = EVENT_LABEL[ev.kind] || ev.kind;
          // "Where is the task NOW?" chip — shown when the transition
          // is historical and the board column no longer reflects it.
          // Suppressed when new_status equals current_status (live row)
          // so the latest event doesn't render redundant noise like
          // `in_progress -> complete   now: complete`.
          const current = ev.currentStatus;
          const showCurrent = Boolean(current) && current !== ev.newStatus;
          return (
            <div
              key={ev.id}
              style={{
                padding: '6px 10px',
                borderBottom: '1px dotted var(--col-border)',
                fontSize: 10.5,
                lineHeight: 1.4,
                display: 'flex',
                gap: 6,
                alignItems: 'flex-start',
              }}
            >
              <span
                style={{ color: 'var(--ink-faint)', flexShrink: 0 }}
                title={ev.transitionedAt ? new Date(ev.transitionedAt * 1000).toLocaleString() : undefined}
              >
                {ev.t}
              </span>
              <AgentPip agentId={ev.agent} />
              <span
                style={{
                  color,
                  fontWeight: 700,
                  fontSize: 9,
                  flexShrink: 0,
                  padding: '1px 4px',
                  background: `${color}18`,
                  borderRadius: 2,
                  textTransform: 'uppercase',
                  letterSpacing: '.04em',
                }}
              >
                {label}
              </span>
              <div style={{ flex: 1, minWidth: 0, color: 'var(--ink)' }}>
                {ev.taskId && (
                  <span style={{ color: 'var(--accent)', fontWeight: 600, marginRight: 4 }}>
                    {ev.taskId}
                  </span>
                )}
                <span style={{ color: 'var(--ink-soft)' }}>{ev.message}</span>
                {showCurrent && (
                  <span
                    title="Current status in DB (the history event may be older than this)"
                    style={{
                      marginLeft: 6,
                      padding: '1px 5px',
                      borderRadius: 3,
                      fontSize: 9,
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      letterSpacing: '.04em',
                      color: 'var(--ink-soft)',
                      background: 'var(--board-grain)',
                      border: '1px solid var(--col-border)',
                    }}
                  >
                    now: {current}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <div
        style={{
          padding: '8px 12px',
          borderTop: '1px solid var(--col-border)',
          fontSize: 10,
          color: 'var(--ink-faint)',
          display: 'flex',
          justifyContent: 'space-between',
        }}
      >
        <span>agent file-watch · human drag/create</span>
        <span>{events.length} events</span>
      </div>
    </div>
  );
}

// ============================================================
// Tweaks panel
// ============================================================
