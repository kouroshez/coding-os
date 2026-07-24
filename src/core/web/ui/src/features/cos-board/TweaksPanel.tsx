import { useThemeStore } from '@/store/theme-store';
import type { BoardTweaks } from './types';

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
