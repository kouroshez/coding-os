import { type CSSProperties, type ReactNode } from 'react';
import { AgentBadge } from './AgentBadges';
import { alpha, lanePalette, useAgentCatalog, isPresenceAgent } from './board-shared';
import type { Highlight, TaskCounts } from './board-shared';
import { KIND_COLORS } from './kindColors';
import type { SwimlaneDTO } from './types';

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
