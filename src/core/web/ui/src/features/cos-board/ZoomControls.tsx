import { type ReactNode } from 'react';

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
