// Scrumban board components — whiteboard aesthetic
const { useState, useEffect, useRef, useMemo, useCallback } = React;

// ---------- MARKER / INK HELPERS ----------
function MarkerLine({ className = '', style = {}, variant = 'h' }) {
  // hand-drawn underline / column divider
  const path = variant === 'h'
    ? "M2 6 C 40 2, 80 9, 120 4 S 200 8, 240 5 S 320 7, 398 4"
    : "M4 2 C 2 40, 8 80, 3 120 S 7 200, 4 240 S 9 320, 4 398";
  return (
    <svg className={className} style={style} viewBox={variant === 'h' ? '0 0 400 10' : '0 0 10 400'} preserveAspectRatio="none">
      <path d={path} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" opacity="0.55" />
    </svg>
  );
}

function TapeStrip({ color = '#f5d76e', width = 44, rotate = -8, style = {} }) {
  return (
    <div style={{
      position: 'absolute',
      width, height: 18,
      background: `linear-gradient(180deg, ${color}dd 0%, ${color}aa 50%, ${color}dd 100%)`,
      transform: `rotate(${rotate}deg)`,
      boxShadow: '0 1px 2px rgba(0,0,0,.15)',
      borderLeft: '1px dashed rgba(0,0,0,.08)',
      borderRight: '1px dashed rgba(0,0,0,.08)',
      ...style,
    }} />
  );
}

// ---------- PRIORITY BORDER ----------
function priorityStyle(priority) {
  switch (priority) {
    case 'P0': return { outline: '2.5px double #c0392b', outlineOffset: 1 };
    case 'P1': return { outline: '1.5px solid #ea580c' };
    case 'P2': return { outline: '1px dashed #8a8378' };
    case 'P3': return { outline: '1px dotted #b8b0a3' };
    default:   return {};
  }
}

// ---------- AGENT PIP ----------
function AgentPip({ agentId, title }) {
  const a = window.AGENTS.find(x => x.id === agentId);
  if (!a) return null;
  return (
    <span title={title || a.session} style={{
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      width: 18, height: 18, borderRadius: '50%',
      background: a.color, color: 'white', fontSize: 10, fontWeight: 700,
      fontFamily: 'JetBrains Mono, monospace',
      boxShadow: '0 1px 2px rgba(0,0,0,.25)',
      border: '1.5px solid rgba(255,255,255,.8)',
    }}>{a.glyph}</span>
  );
}

// ---------- TASK CARD (sticky note) ----------
function TaskCard({ task, density, agentSurface, onDragStart, onDragEnd, isDragging, onClick, highlight, quietMode }) {
  const kind = window.KIND_COLORS[task.kind] || window.KIND_COLORS.feature;
  const lane = window.SWIMLANES.find(l => l.id === task.swimlane);
  const cozy = density === 'cozy';

  // highlight logic
  let isHighlighted = !highlight;
  if (highlight) {
    if (highlight.type === 'kind') isHighlighted = task.kind === highlight.value;
    else if (highlight.type === 'swim') isHighlighted = task.swimlane === highlight.value;
    else if (highlight.type === 'priority') isHighlighted = task.priority === highlight.value;
  }
  const dimmed = highlight && !isHighlighted;

  // quiet mode: subdued body, kind only as chip/dot
  const bg = quietMode
    ? `linear-gradient(155deg, var(--board) 0%, var(--col-bg) 100%)`
    : `linear-gradient(155deg, ${kind.bg} 0%, ${kind.bg2} 100%)`;
  const lastLog = task.workLog[task.workLog.length - 1];

  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, task)}
      onDragEnd={onDragEnd}
      onClick={() => onClick && onClick(task)}
      className="sticky-card"
      style={{
        position: 'relative',
        padding: cozy ? '10px 11px 9px' : '7px 9px 6px',
        margin: cozy ? '0 0 10px' : '0 0 6px',
        fontFamily: "'Kalam', 'Caveat', cursive",
        fontSize: cozy ? 14 : 12.5,
        lineHeight: 1.25,
        color: '#1a1814',
        background: bg,
        borderRadius: '2px 3px 2px 3px',
        transform: `rotate(${task.rotation}deg)`,
        boxShadow: isDragging
          ? '0 18px 26px rgba(0,0,0,.25), 0 3px 6px rgba(0,0,0,.18)'
          : dimmed
            ? '0 1px 2px rgba(0,0,0,.08)'
            : '0 2px 4px rgba(0,0,0,.12), 0 6px 10px -6px rgba(0,0,0,.18)',
        cursor: 'grab',
        transition: 'transform .15s ease, box-shadow .15s ease, opacity .15s ease, filter .15s ease',
        opacity: isDragging ? 0.4 : dimmed ? 0.22 : 1,
        filter: dimmed ? 'grayscale(0.7)' : 'none',
        borderLeft: `5px solid ${lane?.accent || '#888'}`,
        ...priorityStyle(task.priority),
      }}
    >
      {/* quiet mode: big corner kind dot */}
      {quietMode && (
        <span style={{
          position: 'absolute', top: 6, right: 6,
          width: 10, height: 10, borderRadius: '50%',
          background: kind.chip,
          boxShadow: '0 1px 2px rgba(0,0,0,.2)',
        }} title={kind.label} />
      )}
      {/* tape */}
      {task.status === 'emergency' && (
        <TapeStrip color="#ff6b6b" rotate={-6} style={{ top: -9, left: '50%', marginLeft: -22 }} />
      )}

      {/* top row: id + kind chip + priority + agent pip */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: cozy ? 4 : 2 }}>
        <span style={{
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: cozy ? 10 : 9, fontWeight: 700,
          color: '#3a3530', letterSpacing: '.02em',
        }}>{task.id}</span>
        <span style={{
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 9, fontWeight: 700, color: '#fff',
          background: kind.chip, padding: '1px 5px', borderRadius: 2,
          letterSpacing: '.04em', textTransform: 'uppercase',
        }}>{kind.label}</span>
        <span style={{
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 9, fontWeight: 700,
          color: task.priority === 'P0' ? '#b91c1c' : task.priority === 'P1' ? '#c2410c' : '#6b665e',
        }}>{task.priority}</span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 3, alignItems: 'center' }}>
          {task.stale && (
            <span title="stale — no work log in 3d" style={{ fontSize: 11 }}>⚠︎</span>
          )}
          {task.agent && agentSurface && <AgentPip agentId={task.agent} />}
        </span>
      </div>

      {/* title */}
      <div style={{
        fontWeight: 700,
        fontSize: cozy ? 15 : 13.5,
        color: '#141210',
        textWrap: 'pretty',
        marginBottom: cozy ? 6 : 3,
        fontFamily: "'Kalam', cursive",
      }}>{task.title}</div>

      {/* meta row: appetite + epic + labels */}
      <div style={{
        display: 'flex', flexWrap: 'wrap', gap: 4, alignItems: 'center',
        fontFamily: 'JetBrains Mono, monospace', fontSize: 9,
        color: '#4a4540', marginBottom: cozy && (task.workLog.length || task.blockedReason) ? 5 : 0,
      }}>
        <span style={{ background: 'rgba(0,0,0,.06)', padding: '1px 5px', borderRadius: 2 }}>◷ {task.appetite}</span>
        {task.epic && (
          <span style={{
            background: 'rgba(0,0,0,.08)', padding: '1px 5px', borderRadius: 2,
            fontWeight: 600,
          }}>#{task.epic}</span>
        )}
        {task.labels.slice(0, cozy ? 3 : 2).map(l => (
          <span key={l} style={{ color: '#6b665e' }}>·{l}</span>
        ))}
      </div>

      {/* work log preview (agent surface + cozy only) */}
      {agentSurface && cozy && lastLog && (
        <div style={{
          marginTop: 6,
          paddingTop: 5,
          borderTop: '1px dashed rgba(0,0,0,.2)',
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 9.5,
          color: '#3a3530',
          lineHeight: 1.35,
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}>
          ↳ {lastLog.replace(/^\d{4}-\d{2}-\d{2} \[[^\]]+\]:\s*/, '')}
        </div>
      )}

      {/* blocked reason */}
      {task.blockedReason && cozy && (
        <div style={{
          marginTop: 5, padding: '4px 6px',
          background: 'rgba(192,57,43,.12)',
          border: '1px dashed rgba(192,57,43,.5)',
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 9.5, color: '#8b2318', lineHeight: 1.3,
        }}>⛔ {task.blockedReason}</div>
      )}
    </div>
  );
}

// ---------- COLUMN HEADER ----------
function ColumnHeader({ col, count, wipViolated, showWipViolation }) {
  const violated = showWipViolation && col.wip != null && count > col.wip;
  return (
    <div style={{
      position: 'sticky', top: 0, zIndex: 3,
      padding: '10px 12px 8px',
      background: violated ? 'rgba(192,57,43,.12)' : 'transparent',
      borderBottom: '2px solid var(--line)',
      textAlign: 'center',
    }}>
      <div style={{
        fontFamily: "'Permanent Marker', cursive",
        fontSize: 17, letterSpacing: '.08em',
        color: violated ? 'var(--red-ink)' : 'var(--line)',
        textTransform: 'uppercase',
        animation: violated ? 'shake 0.6s infinite' : 'none',
      }}>
        {col.label}
      </div>
      <div style={{
        fontFamily: "'Caveat', cursive",
        fontSize: 13,
        color: 'var(--ink-soft)',
        marginTop: -2,
      }}>{col.sub}</div>
      <div style={{
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 10,
        color: violated ? 'var(--red-ink)' : 'var(--ink-faint)',
        marginTop: 2, fontWeight: violated ? 700 : 500,
      }}>
        {count}{col.wip != null ? ` / ${col.wip} wip` : ''}
        {violated && ' ⚠'}
      </div>
    </div>
  );
}

// ---------- SWIMLANE LABEL ----------
function SwimlaneLabel({ lane, taskCount, onCollapse }) {
  return (
    <div style={{
      position: 'sticky', left: 0, zIndex: 4,
      width: 130, minWidth: 130, flexShrink: 0,
      padding: '12px 10px',
      background: 'var(--board)',
      borderRight: `3px solid ${lane.accent}`,
      display: 'flex', flexDirection: 'column', justifyContent: 'center',
    }}>
      {onCollapse && (
        <button
          onClick={onCollapse} title="Collapse lane"
          style={{
            position: 'absolute', top: 6, right: 6,
            width: 18, height: 18,
            background: 'transparent', border: 'none',
            color: 'var(--ink-faint)', cursor: 'pointer',
            fontSize: 12, lineHeight: 1, padding: 0,
            fontFamily: 'JetBrains Mono, monospace',
          }}
        >▾</button>
      )}
      <div style={{
        fontFamily: "'Permanent Marker', cursive",
        fontSize: 15, color: lane.accent,
        letterSpacing: '.02em',
        writingMode: 'horizontal-tb',
      }}>{lane.label}</div>
      <div style={{
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 9, color: 'var(--ink-faint)', marginTop: 2,
      }}>{taskCount} tasks</div>
      <div style={{
        width: 40, height: 3, marginTop: 6,
        background: lane.accent, borderRadius: 2, opacity: .8,
      }} />
    </div>
  );
}

// ---------- DROP ZONE CELL ----------
function Cell({ tasks, col, lane, density, agentSurface, onDragOver, onDrop, isDragTarget, draggingId, onDragStart, onDragEnd, onCardClick, highlight, quietMode }) {
  const violated = col.wip != null && tasks.length > col.wip;
  return (
    <div
      onDragOver={onDragOver}
      onDrop={onDrop}
      style={{
        flex: '1 1 0', minWidth: 190,
        padding: density === 'cozy' ? '10px 10px 8px' : '6px 7px 5px',
        borderRight: '1px dashed var(--col-border)',
        background: isDragTarget
          ? 'rgba(217, 108, 44, .08)'
          : violated
            ? 'rgba(192,57,43,.04)'
            : 'transparent',
        minHeight: 120,
        transition: 'background .1s ease',
      }}
    >
      {tasks.map(t => (
        <TaskCard
          key={t.id} task={t}
          density={density} agentSurface={agentSurface}
          highlight={highlight} quietMode={quietMode}
          isDragging={draggingId === t.id}
          onDragStart={onDragStart}
          onDragEnd={onDragEnd}
          onClick={onCardClick}
        />
      ))}
      {tasks.length === 0 && (
        <div style={{
          fontFamily: "'Caveat', cursive",
          fontSize: 14, color: 'var(--ink-faint)',
          textAlign: 'center', padding: '20px 4px',
          opacity: .5,
        }}>— empty —</div>
      )}
    </div>
  );
}

Object.assign(window, {
  MarkerLine, TapeStrip, TaskCard, ColumnHeader, SwimlaneLabel, Cell, AgentPip,
  priorityStyle,
});
