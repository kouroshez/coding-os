// Legend — kind + swimlane + priority swatches with hover-highlight
const { useState: useStateL } = React;

function Swatch({ bg, border, size = 14, shape = 'square' }) {
  return (
    <span style={{
      display: 'inline-block',
      width: size, height: size,
      background: bg,
      border: border || '1px solid rgba(0,0,0,.15)',
      borderRadius: shape === 'round' ? '50%' : 2,
      flexShrink: 0,
      boxShadow: '0 1px 1px rgba(0,0,0,.08)',
    }} />
  );
}

function LegendSection({ title, children }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 9, fontWeight: 700,
        color: 'var(--ink-faint)',
        letterSpacing: '.08em', textTransform: 'uppercase',
        marginBottom: 5,
      }}>{title}</div>
      {children}
    </div>
  );
}

function LegendRow({ swatch, label, sub, active, dim, onEnter, onLeave, onClick }) {
  return (
    <div
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 7,
        padding: '3px 5px',
        fontFamily: 'Inter, sans-serif',
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

function Legend({ open, onClose, highlight, setHighlight, filterKind, setFilterKind, filterSwim, setFilterSwim, taskCounts }) {
  if (!open) return null;

  const kinds = Object.entries(window.KIND_COLORS);
  const swims = window.SWIMLANES;

  return (
    <div style={{
      position: 'fixed', top: 56, right: 14, bottom: 14, zIndex: 50,
      width: 280,
      background: 'var(--col-bg)',
      border: '1px solid var(--col-border)',
      borderRadius: 6,
      boxShadow: '0 20px 40px -10px rgba(0,0,0,.3)',
      fontFamily: 'Inter, sans-serif',
      overflowY: 'auto',
      display: 'flex', flexDirection: 'column',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '8px 12px',
        borderBottom: '1px solid var(--col-border)',
      }}>
        <div style={{
          fontFamily: "'Permanent Marker', cursive",
          fontSize: 13, letterSpacing: '.04em',
          color: 'var(--accent)',
        }}>LEGEND</div>
        <button onClick={onClose} style={{
          background: 'none', border: 'none', color: 'var(--ink-faint)',
          cursor: 'pointer', fontSize: 14, lineHeight: 1, padding: 0,
        }}>×</button>
      </div>

      <div style={{ padding: 10 }}>
        <LegendSection title="Kind — card body">
          {kinds.map(([k, v]) => {
            const active = filterKind === k || highlight?.type === 'kind' && highlight?.value === k;
            const dim = (filterKind !== 'all' && filterKind !== k) ||
                        (highlight?.type === 'kind' && highlight?.value !== k);
            return (
              <LegendRow key={k}
                swatch={<Swatch bg={`linear-gradient(155deg, ${v.bg} 0%, ${v.bg2} 100%)`} border={`1px solid ${v.chip}`} />}
                label={v.label}
                sub={taskCounts.kind[k] || 0}
                active={active} dim={dim}
                onEnter={() => setHighlight({ type: 'kind', value: k })}
                onLeave={() => setHighlight(null)}
                onClick={() => setFilterKind(filterKind === k ? 'all' : k)}
              />
            );
          })}
        </LegendSection>

        <LegendSection title="Swimlane — left band">
          {swims.map(lane => {
            const active = filterSwim === lane.id || (highlight?.type === 'swim' && highlight?.value === lane.id);
            const dim = (filterSwim !== 'all' && filterSwim !== lane.id) ||
                        (highlight?.type === 'swim' && highlight?.value !== lane.id);
            return (
              <LegendRow key={lane.id}
                swatch={<div style={{
                  width: 14, height: 14,
                  background: 'var(--board)',
                  borderLeft: `4px solid ${lane.accent}`,
                  border: '1px solid rgba(0,0,0,.15)',
                  flexShrink: 0,
                }} />}
                label={lane.label}
                sub={taskCounts.swim[lane.id] || 0}
                active={active} dim={dim}
                onEnter={() => setHighlight({ type: 'swim', value: lane.id })}
                onLeave={() => setHighlight(null)}
                onClick={() => setFilterSwim(filterSwim === lane.id ? 'all' : lane.id)}
              />
            );
          })}
        </LegendSection>

        <LegendSection title="Priority — outline">
          {[
            { id: 'P0', label: 'P0 · critical',   style: { outline: '2.5px double #c0392b', outlineOffset: 1 } },
            { id: 'P1', label: 'P1 · high',       style: { outline: '1.5px solid #ea580c' } },
            { id: 'P2', label: 'P2 · normal',     style: { outline: '1px dashed #8a8378' } },
            { id: 'P3', label: 'P3 · low',        style: { outline: '1px dotted #b8b0a3' } },
          ].map(p => {
            const active = highlight?.type === 'priority' && highlight?.value === p.id;
            const dim = highlight?.type === 'priority' && highlight?.value !== p.id;
            return (
              <LegendRow key={p.id}
                swatch={<div style={{
                  width: 16, height: 12,
                  background: 'rgba(0,0,0,.04)',
                  ...p.style,
                  flexShrink: 0,
                }} />}
                label={p.label}
                sub={taskCounts.priority[p.id] || 0}
                active={active} dim={dim}
                onEnter={() => setHighlight({ type: 'priority', value: p.id })}
                onLeave={() => setHighlight(null)}
              />
            );
          })}
        </LegendSection>

        <LegendSection title="Agent — corner pip">
          <div style={{ display: 'flex', gap: 8, padding: '3px 5px' }}>
            {window.AGENTS.map(a => (
              <div key={a.id} style={{
                display: 'flex', alignItems: 'center', gap: 5,
                fontSize: 11, color: 'var(--ink)',
              }}>
                <AgentPip agentId={a.id} />
                <span>{a.id}</span>
              </div>
            ))}
          </div>
        </LegendSection>

        <div style={{
          fontFamily: 'JetBrains Mono, monospace', fontSize: 9,
          color: 'var(--ink-faint)', lineHeight: 1.5,
          paddingTop: 8, marginTop: 4,
          borderTop: '1px dashed var(--col-border)',
        }}>
          hover row → highlight · click kind/swim → filter
        </div>
      </div>
    </div>
  );
}

window.Legend = Legend;
