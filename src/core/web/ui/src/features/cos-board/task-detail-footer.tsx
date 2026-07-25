const actionBtn = {
  background: 'transparent',
  border: '1px solid var(--col-border)',
  color: 'var(--ink-soft)',
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: 11,
  padding: '3px 12px',
  borderRadius: 3,
  cursor: 'pointer',
} as const;

interface TaskDetailFooterProps {
  editing: boolean;
  saving: boolean;
  saveError: string | null;
  isReady: boolean;
  canMarkReady: boolean;
  onEdit: () => void;
  onSave: () => void;
  onCancel: () => void;
  onToggleReady: () => void;
}

/** Drawer action bar — edit/save/cancel plus the icebox ready toggle. */
export function TaskDetailFooter({
  editing,
  saving,
  saveError,
  isReady,
  canMarkReady,
  onEdit,
  onSave,
  onCancel,
  onToggleReady,
}: TaskDetailFooterProps) {
  return (
    <div
      style={{
        flex: '0 0 auto',
        padding: '8px 16px',
        borderTop: '1px solid var(--col-border)',
        background: 'var(--board-grain)',
        display: 'flex',
        gap: 6,
        alignItems: 'center',
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 10.5,
        color: 'var(--ink-faint)',
      }}
    >
      {editing ? (
        <>
          <button
            type="button"
            onClick={onSave}
            disabled={saving}
            style={{
              ...actionBtn,
              background: 'var(--accent)',
              border: '1px solid var(--accent)',
              color: '#fff',
              cursor: saving ? 'default' : 'pointer',
              opacity: saving ? 0.6 : 1,
            }}
          >
            {saving ? 'saving…' : '✓ save'}
          </button>
          <button type="button" onClick={onCancel} disabled={saving} style={actionBtn}>
            cancel
          </button>
          {saveError && <span style={{ color: '#dc2626' }}>{saveError}</span>}
        </>
      ) : (
        <>
          <button type="button" onClick={onEdit} style={actionBtn}>
            ✎ edit
          </button>
          {canMarkReady && (
            <button
              type="button"
              onClick={onToggleReady}
              style={{ ...actionBtn, color: isReady ? 'var(--accent)' : 'var(--ink-soft)' }}
            >
              {isReady ? '✓ ready · unmark' : '○ mark ready'}
            </button>
          )}
        </>
      )}
      <span style={{ flex: 1 }} />
      <span style={{ opacity: 0.7 }}>esc close</span>
    </div>
  );
}
