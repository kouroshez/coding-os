// Tweaks panel — edit mode for cos board
const { useState: useStateT, useEffect: useEffectT } = React;

function Toggle({ on, onChange, label, sub }) {
  return (
    <label style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '7px 4px', cursor: 'pointer', userSelect: 'none',
    }}>
      <div
        onClick={() => onChange(!on)}
        style={{
          width: 32, height: 18, borderRadius: 10,
          background: on ? 'var(--accent)' : 'rgba(0,0,0,.18)',
          position: 'relative', transition: 'background .15s ease',
          flexShrink: 0,
        }}>
        <div style={{
          position: 'absolute', top: 2, left: on ? 16 : 2,
          width: 14, height: 14, borderRadius: '50%',
          background: 'white', transition: 'left .15s ease',
          boxShadow: '0 1px 2px rgba(0,0,0,.2)',
        }} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--ink)' }}>{label}</div>
        {sub && <div style={{ fontSize: 10, color: 'var(--ink-faint)', marginTop: 1 }}>{sub}</div>}
      </div>
    </label>
  );
}

function Seg({ value, options, onChange, label }) {
  return (
    <div style={{ padding: '7px 4px' }}>
      <div style={{ fontSize: 11, color: 'var(--ink-soft)', marginBottom: 5, fontWeight: 500 }}>{label}</div>
      <div style={{ display: 'flex', gap: 2, background: 'rgba(0,0,0,.08)', padding: 2, borderRadius: 5 }}>
        {options.map(o => (
          <button key={o.value} onClick={() => onChange(o.value)} style={{
            flex: 1, padding: '5px 6px', fontSize: 11,
            fontFamily: 'Inter, sans-serif', fontWeight: 500,
            background: value === o.value ? 'var(--board)' : 'transparent',
            color: value === o.value ? 'var(--ink)' : 'var(--ink-soft)',
            border: 'none', borderRadius: 4, cursor: 'pointer',
            boxShadow: value === o.value ? '0 1px 2px rgba(0,0,0,.1)' : 'none',
            transition: 'all .12s ease',
          }}>{o.label}</button>
        ))}
      </div>
    </div>
  );
}

function TweaksPanel({ tweaks, setTweaks, visible, onClose }) {
  if (!visible) return null;
  const set = (key, val) => {
    const next = { ...tweaks, [key]: val };
    setTweaks(next);
    window.parent?.postMessage({ type: '__edit_mode_set_keys', edits: { [key]: val } }, '*');
  };

  const kinds = [
    { value: 'all', label: 'all' },
    ...Object.keys(window.KIND_COLORS).map(k => ({ value: k, label: window.KIND_COLORS[k].label })),
  ];
  const epics = [{ value: 'all', label: 'all' }, ...window.EPICS.map(e => ({ value: e.id, label: e.id }))];

  return (
    <div style={{
      position: 'fixed', bottom: 16, right: 16, zIndex: 100,
      width: 280, maxHeight: 'calc(100vh - 40px)', overflowY: 'auto',
      background: 'var(--col-bg)',
      border: '1px solid var(--col-border)',
      borderRadius: 6,
      boxShadow: '0 20px 40px -10px rgba(0,0,0,.3), 0 6px 12px rgba(0,0,0,.15)',
      fontFamily: 'Inter, sans-serif',
      color: 'var(--ink)',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 12px 8px',
        borderBottom: '1px solid var(--col-border)',
      }}>
        <div style={{
          fontFamily: "'Permanent Marker', cursive",
          fontSize: 15, letterSpacing: '.04em',
          color: 'var(--accent)',
        }}>TWEAKS</div>
        <button onClick={onClose} style={{
          background: 'none', border: 'none', color: 'var(--ink-faint)',
          cursor: 'pointer', fontSize: 16, padding: 0, lineHeight: 1,
        }}>×</button>
      </div>
      <div style={{ padding: '6px 10px 12px' }}>
        <Seg label="Theme" value={tweaks.theme}
             options={[{ value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' }]}
             onChange={v => set('theme', v)} />
        <Seg label="Aesthetic" value={tweaks.aesthetic}
             options={[{ value: 'whiteboard', label: 'Whiteboard' }, { value: 'graph', label: 'Graph paper' }, { value: 'terminal', label: 'Terminal' }]}
             onChange={v => set('aesthetic', v)} />
        <Seg label="Density" value={tweaks.density}
             options={[{ value: 'cozy', label: 'Cozy' }, { value: 'compact', label: 'Compact' }]}
             onChange={v => set('density', v)} />
        <div style={{ height: 1, background: 'var(--col-border)', margin: '6px 4px' }} />
        <Toggle on={tweaks.quietMode} onChange={v => set('quietMode', v)}
                label="Quiet mode" sub="subdued cards + kind as corner dot" />
        <Toggle on={tweaks.agentSurface} onChange={v => set('agentSurface', v)}
                label="Agent surface" sub="pips, work log stream, hook events" />
        <Toggle on={tweaks.showWipViolation} onChange={v => set('showWipViolation', v)}
                label="WIP violation state" sub="column flashes red when over cap" />
        <div style={{ height: 1, background: 'var(--col-border)', margin: '6px 4px' }} />
        <Seg label="Filter — kind" value={tweaks.filterKind}
             options={kinds} onChange={v => set('filterKind', v)} />
        <Seg label="Filter — epic" value={tweaks.filterEpic}
             options={epics} onChange={v => set('filterEpic', v)} />
      </div>
    </div>
  );
}

window.TweaksPanel = TweaksPanel;
