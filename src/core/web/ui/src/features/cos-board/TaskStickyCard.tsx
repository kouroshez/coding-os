import { type DragEvent } from 'react';
import { alpha, priorityStyle, useAgentCatalog } from './board-shared';
import type { Highlight } from './board-shared';
import { agentForSession } from './useBoardStream';
import { kindStyle } from './kindColors';
import { LiveAgentPip } from './AgentBadges';
import type { BoardListCard, SwimlaneDTO } from './types';

export function SwimlaneLabel({
  lane,
  palette,
  taskCount,
  onCollapse,
}: {
  lane: SwimlaneDTO;
  palette: { color: string; accent: string };
  taskCount: number;
  onCollapse: () => void;
}) {
  return (
    <div
      style={{
        position: 'sticky',
        left: 0,
        zIndex: 4,
        width: 130,
        minWidth: 130,
        flexShrink: 0,
        alignSelf: 'stretch',
        padding: '12px 10px',
        background: `linear-gradient(90deg, ${alpha(palette.color, 0.14)} 0%, var(--board) 100%)`,
        borderRight: `3px solid ${palette.accent}`,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        boxSizing: 'border-box',
      }}
    >
      <button
        type="button"
        onClick={onCollapse}
        title="Collapse lane"
        style={{
          position: 'absolute',
          top: 6,
          right: 6,
          width: 18,
          height: 18,
          background: 'transparent',
          border: 'none',
          color: 'var(--ink-faint)',
          cursor: 'pointer',
          fontSize: 12,
          lineHeight: 1,
          padding: 0,
          fontFamily: "'JetBrains Mono', monospace",
        }}
      >
        ▾
      </button>
      <div
        style={{
          fontFamily: 'inherit',
          fontSize: 15,
          color: palette.accent,
          letterSpacing: '.02em',
          whiteSpace: 'normal',
          overflowWrap: 'anywhere',
          wordBreak: 'break-word',
          lineHeight: 1.2,
          maxWidth: '100%',
        }}
      >
        {lane.label}
      </div>
      <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, color: 'var(--ink-faint)', marginTop: 2 }}>
        {taskCount} tasks
      </div>
      <div style={{ width: 40, height: 3, marginTop: 6, background: palette.accent, borderRadius: 2, opacity: 0.9 }} />
    </div>
  );
}

// ============================================================
// Task sticky card
// ============================================================
export function TaskStickyCard({
  task,
  laneColor,
  laneAccent,
  density,
  quietMode,
  agentSurface,
  highlight,
  draggingId,
  onDragStart,
  onDragEnd,
  onOpen,
}: {
  task: BoardListCard;
  laneColor: string;
  laneAccent: string;
  density: 'cozy' | 'compact';
  quietMode: boolean;
  agentSurface: boolean;
  highlight: Highlight | null;
  draggingId: string;
  onDragStart: (e: DragEvent, t: BoardListCard) => void;
  onDragEnd: () => void;
  onOpen: (t: BoardListCard) => void;
}) {
  const kind = kindStyle(task.kind);
  const cozy = density === 'cozy';
  const agentCatalog = useAgentCatalog();

  let isHighlighted = !highlight;
  if (highlight) {
    if (highlight.type === 'kind') isHighlighted = task.kind === highlight.value;
    else if (highlight.type === 'swim') isHighlighted = task.swimlane === highlight.value;
    else if (highlight.type === 'priority') isHighlighted = task.priority === highlight.value;
  }
  const dimmed = highlight != null && !isHighlighted;
  const isDragging = draggingId === task.id;

  // Card body colour = swimlane (domain). Kind is conveyed by the chip
  // next to TASK-ID, not the body — so "all Graph OS cards look green, all
  // Core cards look gray, regardless of whether they're bugs or features."
  const bg = quietMode
    ? 'linear-gradient(155deg, var(--board) 0%, var(--col-bg) 100%)'
    : `linear-gradient(155deg, ${alpha(laneColor, 0.16)} 0%, ${alpha(laneColor, 0.07)} 100%)`;

  const agentId = task.agent_session
    ? agentForSession(task.agent_session, agentCatalog.map((a) => a.id))
    : null;

  return (
    <div
      draggable
      role="button"
      tabIndex={0}
      aria-label={`Open task ${task.id}: ${task.title}`}
      onDragStart={(e) => onDragStart(e, task)}
      onDragEnd={onDragEnd}
      onClick={() => onOpen(task)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onOpen(task);
        }
      }}
      className="sticky-card"
      style={{
        position: 'relative',
        padding: cozy ? '10px 11px 9px' : '7px 9px 6px',
        margin: cozy ? '0 0 10px' : '0 0 6px',
        fontFamily: 'inherit',
        fontSize: cozy ? 14 : 12.5,
        lineHeight: 1.25,
        color: 'var(--cos-text)',
        background: bg,
        borderRadius: '8px',
        transform: 'none',
        boxShadow: isDragging
          ? '0 18px 26px rgba(0,0,0,.25), 0 3px 6px rgba(0,0,0,.18)'
          : dimmed
            ? '0 1px 2px rgba(0,0,0,.08)'
            : '0 2px 4px rgba(0,0,0,.12), 0 6px 10px -6px rgba(0,0,0,.18)',
        cursor: 'grab',
        transition: 'transform .15s ease, box-shadow .15s ease, opacity .15s ease, filter .15s ease',
        opacity: isDragging ? 0.4 : dimmed ? 0.22 : 1,
        filter: dimmed ? 'grayscale(0.7)' : 'none',
        borderLeft: `5px solid ${laneAccent || '#888'}`,
        overflow: 'hidden',
        ...priorityStyle(task.priority),
      }}
    >
      {quietMode && (
        <span
          style={{
            position: 'absolute',
            top: 6,
            right: 6,
            width: 10,
            height: 10,
            borderRadius: '50%',
            background: kind.chip,
            boxShadow: '0 1px 2px rgba(0,0,0,.2)',
          }}
          title={kind.label}
        />
      )}
      {task.status === 'emergency' && (
        <div
          style={{
            position: 'absolute',
            width: 44,
            height: 18,
            top: -9,
            left: '50%',
            marginLeft: -22,
            background: 'linear-gradient(180deg, #ff6b6bdd 0%, #ff6b6baa 50%, #ff6b6bdd 100%)',
            transform: 'rotate(-6deg)',
            boxShadow: '0 1px 2px rgba(0,0,0,.15)',
            borderLeft: '1px dashed rgba(0,0,0,.08)',
            borderRight: '1px dashed rgba(0,0,0,.08)',
          }}
        />
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: cozy ? 4 : 2 }}>
        <span
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: cozy ? 10 : 9,
            fontWeight: 700,
            color: 'var(--cos-muted)',
            letterSpacing: '.02em',
          }}
        >
          {task.id}
        </span>
        <span
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 9,
            fontWeight: 700,
            color: kind.chip,
            background: `color-mix(in oklab, ${kind.chip} 20%, transparent)`,
            border: `1px solid color-mix(in oklab, ${kind.chip} 38%, transparent)`,
            padding: '1px 5px',
            borderRadius: 3,
            letterSpacing: '.04em',
            textTransform: 'uppercase',
          }}
        >
          {kind.label}
        </span>
        <span
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 9,
            fontWeight: 700,
            color:
              task.priority === 'P0'
                ? 'var(--cos-err)'
                : task.priority === 'P1'
                  ? 'var(--cos-warn)'
                  : 'var(--cos-muted)',
          }}
        >
          {task.priority}
        </span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 3, alignItems: 'center' }}>
          {agentId && agentSurface && (
            <LiveAgentPip agentId={agentId} session={task.agent_session} />
          )}
        </span>
      </div>

      <div
        style={{
          fontWeight: 700,
          fontSize: cozy ? 15 : 13.5,
          color: 'var(--cos-text)',
          whiteSpace: 'normal',
          overflowWrap: 'anywhere',
          wordBreak: 'break-word',
          hyphens: 'auto',
          maxWidth: '100%',
          marginBottom: cozy ? 6 : 3,
          fontFamily: 'inherit',
        }}
      >
        {task.title}
      </div>

      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 4,
          alignItems: 'center',
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 9,
          color: 'var(--cos-muted)',
          marginBottom: cozy && task.last_log_line ? 5 : 0,
        }}
      >
        <span style={{ background: 'var(--cos-inset)', padding: '1px 5px', borderRadius: 2 }}>
          ◷ {task.appetite || '1d'}
        </span>
        {task.epic && (
          <span style={{ background: 'var(--cos-inset)', padding: '1px 5px', borderRadius: 2, fontWeight: 600 }}>
            #{task.epic}
          </span>
        )}
        {task.status === 'icebox' && (task.labels || []).includes('ready') && (
          <span
            title="Tagged ready — candidate for pickup"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 3,
              background: 'linear-gradient(180deg, #86efac 0%, #4ade80 100%)',
              color: '#14532d',
              padding: '1px 6px',
              borderRadius: 10,
              fontWeight: 800,
              letterSpacing: '.04em',
              textTransform: 'uppercase',
              border: '1px solid #16a34a',
              boxShadow: '0 1px 1px rgba(22,163,74,.25)',
            }}
          >
            ● READY
          </span>
        )}
        {(task.labels || [])
          .filter((l) => l !== 'ready')
          .slice(0, cozy ? 3 : 2)
          .map((l) => (
            <span key={l} style={{ color: 'var(--cos-faint)', overflowWrap: 'anywhere', wordBreak: 'break-word' }}>
              ·{l}
            </span>
          ))}
      </div>

      {agentSurface && cozy && task.last_log_line && (
        <div
          style={{
            marginTop: 6,
            paddingTop: 5,
            borderTop: '1px dashed var(--cos-border)',
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 9.5,
            color: 'var(--cos-muted)',
            lineHeight: 1.35,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          ↳ {task.last_log_line.replace(/^\d{4}-\d{2}-\d{2} \[[^\]]+\]:\s*/, '')}
        </div>
      )}
    </div>
  );
}

