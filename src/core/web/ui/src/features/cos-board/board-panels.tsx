import { type CSSProperties, type ReactNode } from 'react';
import { AgentBadge, AgentPip } from './AgentBadges';
import { alpha, lanePalette, useAgentCatalog, isPresenceAgent, EVENT_COLOR, EVENT_LABEL } from './board-shared';
import type { Highlight, TaskCounts } from './board-shared';
import { KIND_COLORS } from './kindColors';
import { useThemeStore } from '@/store/theme-store';
import type { BoardTweaks, SwimlaneDTO } from './types';
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
export function TweaksPanel({
  open,
  onClose,
  tweaks,
  setTweaks,
  kindOptions,
  epicOptions,
}: {
  open: boolean;
  onClose: () => void;
  tweaks: BoardTweaks;
  setTweaks: (updater: (prev: BoardTweaks) => BoardTweaks) => void;
  kindOptions: { value: string; label: string }[];
  epicOptions: { value: string; label: string }[];
}) {
  if (!open) return null;
  const set = <K extends keyof BoardTweaks>(k: K, v: BoardTweaks[K]) => setTweaks((t) => ({ ...t, [k]: v }));
  return (
    <div
      style={{
        position: 'fixed',
        bottom: 60,
        right: 16,
        zIndex: 100,
        width: 280,
        maxHeight: 'calc(100vh - 220px)',
        overflowY: 'auto',
        background: 'var(--col-bg)',
        border: '1px solid var(--col-border)',
        borderRadius: 6,
        boxShadow: '0 20px 40px -10px rgba(0,0,0,.3), 0 6px 12px rgba(0,0,0,.15)',
        fontFamily: "'Inter', sans-serif",
        color: 'var(--ink)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 12px 8px',
          borderBottom: '1px solid var(--col-border)',
        }}
      >
        <div
          style={{
            fontFamily: 'inherit',
            fontSize: 15,
            letterSpacing: '.04em',
            color: 'var(--accent)',
          }}
        >
          TWEAKS
        </div>
        <button
          type="button"
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--ink-faint)',
            cursor: 'pointer',
            fontSize: 16,
            padding: 0,
            lineHeight: 1,
          }}
        >
          ×
        </button>
      </div>
      <div style={{ padding: '6px 10px 12px' }}>
        <Seg
          label="Theme"
          value={tweaks.theme}
          options={[
            { value: 'light', label: 'Light' },
            { value: 'dark', label: 'Dark' },
          ]}
          onChange={(v) => useThemeStore.getState().setTheme(v as 'light' | 'dark')}
        />
        <Seg
          label="Aesthetic"
          value={tweaks.aesthetic}
          options={[
            { value: 'whiteboard', label: 'Whiteboard' },
            { value: 'graph', label: 'Graph paper' },
            { value: 'terminal', label: 'Terminal' },
          ]}
          onChange={(v) => set('aesthetic', v as BoardTweaks['aesthetic'])}
        />
        <Seg
          label="Density"
          value={tweaks.density}
          options={[
            { value: 'cozy', label: 'Cozy' },
            { value: 'compact', label: 'Compact' },
          ]}
          onChange={(v) => set('density', v as BoardTweaks['density'])}
        />
        <div style={{ height: 1, background: 'var(--col-border)', margin: '6px 4px' }} />
        <Toggle on={tweaks.quietMode} onChange={(v) => set('quietMode', v)} label="Quiet mode" sub="subdued cards + kind as corner dot" />
        <Toggle on={tweaks.agentSurface} onChange={(v) => set('agentSurface', v)} label="Agent surface" sub="pips, work log stream, hook events" />
        <Toggle on={tweaks.showWipViolation} onChange={(v) => set('showWipViolation', v)} label="WIP violation state" sub="column flashes red when over cap" />
        <Toggle on={tweaks.showSwimlanes} onChange={(v) => set('showSwimlanes', v)} label="Swimlane grid" sub="off = flat status columns — every active task visible at a glance" />
        <Toggle on={tweaks.showArchive} onChange={(v) => set('showArchive', v)} label="Show archive column" sub="soft-terminal cold store — hidden by default" />
        <div style={{ height: 1, background: 'var(--col-border)', margin: '6px 4px' }} />
        <Seg label="Filter — kind" value={tweaks.filterKind} options={kindOptions} onChange={(v) => set('filterKind', v)} />
        <Seg label="Filter — epic" value={tweaks.filterEpic} options={epicOptions} onChange={(v) => set('filterEpic', v)} />
      </div>
    </div>
  );
}

function Seg({
  value,
  options,
  onChange,
  label,
}: {
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
  label: string;
}) {
  return (
    <div style={{ padding: '7px 4px' }}>
      <div style={{ fontSize: 11, color: 'var(--ink-soft)', marginBottom: 5, fontWeight: 500 }}>{label}</div>
      <div style={{ display: 'flex', gap: 2, background: 'rgba(0,0,0,.08)', padding: 2, borderRadius: 5, flexWrap: 'wrap' }}>
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            onClick={() => onChange(o.value)}
            style={{
              flex: '1 0 auto',
              padding: '5px 8px',
              fontSize: 11,
              fontFamily: "'Inter', sans-serif",
              fontWeight: 500,
              background: value === o.value ? 'var(--board)' : 'transparent',
              color: value === o.value ? 'var(--ink)' : 'var(--ink-soft)',
              border: 'none',
              borderRadius: 4,
              cursor: 'pointer',
              boxShadow: value === o.value ? '0 1px 2px rgba(0,0,0,.1)' : 'none',
            }}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Toggle({
  on,
  onChange,
  label,
  sub,
}: {
  on: boolean;
  onChange: (v: boolean) => void;
  label: string;
  sub?: string;
}) {
  return (
    <span
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '7px 4px',
        userSelect: 'none',
      }}
    >
      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-label={label}
        onClick={() => onChange(!on)}
        style={{
          width: 32,
          height: 18,
          borderRadius: 10,
          border: 'none',
          padding: 0,
          cursor: 'pointer',
          background: on ? 'var(--accent)' : 'rgba(0,0,0,.18)',
          position: 'relative',
          transition: 'background .15s ease',
          flexShrink: 0,
        }}
      >
        <span
          aria-hidden
          style={{
            position: 'absolute',
            top: 2,
            left: on ? 16 : 2,
            width: 14,
            height: 14,
            borderRadius: '50%',
            background: 'white',
            transition: 'left .15s ease',
            boxShadow: '0 1px 2px rgba(0,0,0,.2)',
          }}
        />
      </button>
      <span style={{ flex: 1, minWidth: 0 }}>
        <span style={{ display: 'block', fontSize: 12, fontWeight: 500, color: 'var(--ink)' }}>
          {label}
        </span>
        {sub && (
          <span style={{ display: 'block', fontSize: 10, color: 'var(--ink-faint)', marginTop: 1 }}>
            {sub}
          </span>
        )}
      </span>
    </span>
  );
}

// ============================================================
// Legend panel
// ============================================================
export function LegendPanel({
  open,
  onClose,
  swimlanes,
  filterKind,
  setFilterKind,
  filterSwim,
  setFilterSwim,
  highlight,
  setHighlight,
  taskCounts,
}: {
  open: boolean;
  onClose: () => void;
  swimlanes: SwimlaneDTO[];
  filterKind: string;
  setFilterKind: (v: string) => void;
  filterSwim: string;
  setFilterSwim: (v: string) => void;
  highlight: Highlight | null;
  setHighlight: (h: Highlight | null) => void;
  taskCounts: TaskCounts;
}) {
  // Hook must run unconditionally — call before the early return (rules-of-hooks).
  const legendAgents = useAgentCatalog();
  if (!open) return null;
  const kinds = Object.entries(KIND_COLORS);
  return (
    <div
      style={{
        position: 'fixed',
        top: 160,
        right: 14,
        bottom: 60,
        zIndex: 50,
        width: 280,
        background: 'var(--col-bg)',
        border: '1px solid var(--col-border)',
        borderRadius: 6,
        boxShadow: '0 20px 40px -10px rgba(0,0,0,.3)',
        fontFamily: "'Inter', sans-serif",
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 12px',
          borderBottom: '1px solid var(--col-border)',
        }}
      >
        <div
          style={{
            fontFamily: 'inherit',
            fontSize: 13,
            letterSpacing: '.04em',
            color: 'var(--accent)',
          }}
        >
          LEGEND
        </div>
        <button
          type="button"
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--ink-faint)',
            cursor: 'pointer',
            fontSize: 14,
            lineHeight: 1,
            padding: 0,
          }}
        >
          ×
        </button>
      </div>

      <div style={{ padding: 10 }}>
        <LegendSection title="Kind — card body">
          {kinds.map(([k, v]) => {
            const active = filterKind === k || (highlight?.type === 'kind' && highlight?.value === k);
            const dim =
              (filterKind !== 'all' && filterKind !== k) ||
              (highlight?.type === 'kind' && highlight?.value !== k);
            return (
              <LegendRow
                key={k}
                swatch={
                  <span
                    style={{
                      display: 'inline-block',
                      width: 14,
                      height: 14,
                      background: `linear-gradient(155deg, ${v.bg} 0%, ${v.bg2} 100%)`,
                      border: `1px solid ${v.chip}`,
                      borderRadius: 2,
                    }}
                  />
                }
                label={v.label}
                sub={String(taskCounts.kind[k] || 0)}
                active={!!active}
                dim={!!dim}
                onEnter={() => setHighlight({ type: 'kind', value: k })}
                onLeave={() => setHighlight(null)}
                onClick={() => setFilterKind(filterKind === k ? 'all' : k)}
              />
            );
          })}
        </LegendSection>

        <LegendSection title="Swimlane — left band">
          {swimlanes.map((lane) => {
            const p = lanePalette(lane);
            const active = filterSwim === lane.id || (highlight?.type === 'swim' && highlight?.value === lane.id);
            const dim =
              (filterSwim !== 'all' && filterSwim !== lane.id) ||
              (highlight?.type === 'swim' && highlight?.value !== lane.id);
            return (
              <LegendRow
                key={lane.id}
                swatch={
                  <span
                    style={{
                      width: 14,
                      height: 14,
                      background: alpha(p.color, 0.3),
                      borderLeft: `4px solid ${p.accent}`,
                      border: '1px solid rgba(0,0,0,.15)',
                      display: 'inline-block',
                    }}
                  />
                }
                label={lane.label}
                sub={String(taskCounts.swim[lane.id] || 0)}
                active={!!active}
                dim={!!dim}
                onEnter={() => setHighlight({ type: 'swim', value: lane.id })}
                onLeave={() => setHighlight(null)}
                onClick={() => setFilterSwim(filterSwim === lane.id ? 'all' : lane.id)}
              />
            );
          })}
        </LegendSection>

        <LegendSection title="Priority — outline">
          {[
            { id: 'P0', label: 'P0 · critical', style: { outline: '2.5px double #c0392b', outlineOffset: 1 } as CSSProperties },
            { id: 'P1', label: 'P1 · high', style: { outline: '1.5px solid #ea580c' } as CSSProperties },
            { id: 'P2', label: 'P2 · normal', style: { outline: '1px dashed #8a8378' } as CSSProperties },
            { id: 'P3', label: 'P3 · low', style: { outline: '1px dotted #b8b0a3' } as CSSProperties },
          ].map((p) => {
            const active = highlight?.type === 'priority' && highlight?.value === p.id;
            const dim = highlight?.type === 'priority' && highlight?.value !== p.id;
            return (
              <LegendRow
                key={p.id}
                swatch={
                  <span
                    style={{
                      width: 16,
                      height: 12,
                      background: 'rgba(0,0,0,.04)',
                      ...p.style,
                      display: 'inline-block',
                    }}
                  />
                }
                label={p.label}
                sub={String(taskCounts.priority[p.id] || 0)}
                active={!!active}
                dim={!!dim}
                onEnter={() => setHighlight({ type: 'priority', value: p.id })}
                onLeave={() => setHighlight(null)}
                onClick={() => {}}
              />
            );
          })}
        </LegendSection>

        <LegendSection title="Agent — corner pip">
          <div style={{ display: 'flex', gap: 8, padding: '3px 5px', flexWrap: 'wrap' }}>
            {legendAgents.filter(isPresenceAgent).map((a) => (
              <div
                key={a.id}
                style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--ink)' }}
              >
                <AgentBadge agentId={a.id} state="active" />
              </div>
            ))}
          </div>
        </LegendSection>
      </div>
    </div>
  );
}

function LegendSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div
        style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 9,
          fontWeight: 700,
          color: 'var(--ink-faint)',
          letterSpacing: '.08em',
          textTransform: 'uppercase',
          marginBottom: 5,
        }}
      >
        {title}
      </div>
      {children}
    </div>
  );
}

function LegendRow({
  swatch,
  label,
  sub,
  active,
  dim,
  onEnter,
  onLeave,
  onClick,
}: {
  swatch: ReactNode;
  label: string;
  sub?: string;
  active: boolean;
  dim: boolean;
  onEnter: () => void;
  onLeave: () => void;
  onClick: () => void;
}) {
  return (
    <div
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 7,
        padding: '3px 5px',
        fontFamily: "'Inter', sans-serif",
        fontSize: 11,
        color: dim ? 'var(--ink-faint)' : 'var(--ink)',
        cursor: 'pointer',
        borderRadius: 3,
        background: active ? 'rgba(217, 108, 44, .15)' : 'transparent',
        opacity: dim ? 0.4 : 1,
        transition: 'opacity .1s ease, background .1s ease',
        userSelect: 'none',
      }}
    >
      {swatch}
      <span style={{ fontWeight: active ? 700 : 500 }}>{label}</span>
      {sub && <span style={{ color: 'var(--ink-faint)', fontSize: 10, marginLeft: 'auto' }}>{sub}</span>}
    </div>
  );
}

// ============================================================
// Zoom controls
// ============================================================
export function ZoomControls({
  zoom,
  setZoom,
  collapsedCount,
  onExpandAll,
  onCollapseEmpty,
}: {
  zoom: number;
  setZoom: (v: number) => void;
  collapsedCount: number;
  onExpandAll: () => void;
  onCollapseEmpty: () => void;
}) {
  const pct = Math.round(zoom * 100);
  return (
    <div
      style={{
        position: 'fixed',
        right: 20,
        bottom: 20,
        zIndex: 45,
        display: 'flex',
        alignItems: 'stretch',
        gap: 6,
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 11,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          background: 'var(--col-bg)',
          border: '1px solid var(--col-border)',
          borderRadius: 4,
          boxShadow: '0 4px 14px rgba(0,0,0,.12)',
          overflow: 'hidden',
        }}
      >
        <ZoomBtn onClick={onCollapseEmpty} title="Collapse empty lanes">
          ⊟ empty
        </ZoomBtn>
        <ZoomDiv />
        <ZoomBtn onClick={onExpandAll} disabled={collapsedCount === 0} title="Expand all">
          ⊞ expand
        </ZoomBtn>
      </div>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          background: 'var(--col-bg)',
          border: '1px solid var(--col-border)',
          borderRadius: 4,
          boxShadow: '0 4px 14px rgba(0,0,0,.12)',
          overflow: 'hidden',
        }}
      >
        <ZoomBtn onClick={() => setZoom(zoom - 0.1)} disabled={zoom <= 0.5} title="Zoom out (⌘-)">
          −
        </ZoomBtn>
        <ZoomDiv />
        <button
          type="button"
          onClick={() => setZoom(1)}
          title="Reset (⌘0)"
          style={{
            padding: '0 10px',
            minWidth: 54,
            height: 30,
            background: 'transparent',
            border: 'none',
            color: pct === 100 ? 'var(--ink-faint)' : 'var(--accent)',
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 11,
            fontWeight: 700,
            cursor: 'pointer',
          }}
        >
          {pct}%
        </button>
        <ZoomDiv />
        <ZoomBtn onClick={() => setZoom(zoom + 0.1)} disabled={zoom >= 1.5} title="Zoom in (⌘+)">
          +
        </ZoomBtn>
        <ZoomDiv />
        <input
          type="range"
          min={0.5}
          max={1.5}
          step={0.05}
          value={zoom}
          onChange={(e) => setZoom(parseFloat(e.target.value))}
          aria-label="Board zoom level"
          style={{ width: 90, margin: '0 10px', accentColor: 'var(--accent)' }}
        />
      </div>
    </div>
  );
}

function ZoomBtn({
  children,
  onClick,
  disabled,
  title,
}: {
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      style={{
        height: 30,
        minWidth: 30,
        padding: '0 9px',
        background: 'transparent',
        border: 'none',
        color: disabled ? 'var(--ink-faint)' : 'var(--ink)',
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 13,
        fontWeight: 600,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.35 : 1,
      }}
    >
      {children}
    </button>
  );
}

function ZoomDiv() {
  return <div style={{ width: 1, background: 'var(--col-border)', alignSelf: 'stretch' }} />;
}
