import { type CSSProperties } from 'react';

const chooserCard: CSSProperties = {
  display: 'flex',
  gap: '.85rem',
  alignItems: 'flex-start',
  textAlign: 'left',
  width: '100%',
  padding: '1rem 1.1rem',
  background: 'var(--board-grain)',
  border: '1px solid var(--col-border)',
  borderRadius: 8,
  cursor: 'pointer',
  color: 'var(--ink)',
  transition: 'border-color .12s ease',
};
const chooserCardTitle: CSSProperties = {
  fontSize: '.98rem',
  fontWeight: 600,
  color: 'var(--ink)',
  marginBottom: '.2rem',
};
const chooserCardDesc: CSSProperties = { fontSize: '.8rem', color: 'var(--ink-soft)', lineHeight: 1.45 };
const chooserCancel: CSSProperties = {
  padding: '.5rem .9rem',
  fontSize: '.8rem',
  fontWeight: 600,
  background: 'transparent',
  color: 'var(--ink-soft)',
  border: '1px solid var(--col-border)',
  borderRadius: 4,
  cursor: 'pointer',
};

// Step 1 of the create-task modal — a plain-language chooser so a non-developer
// sees the AI-draft path up front (it used to be a tiny ghost button almost
// nobody noticed). Picking a path calls back into CreateTaskModal.
export function CreateTaskChooser({
  onClose,
  onAgentMode,
  onManual,
}: {
  onClose: () => void;
  onAgentMode?: () => void;
  onManual: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Create a task"
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 200,
        background: 'rgba(0,0,0,.45)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 20,
        animation: 'fadeIn .15s ease',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 'clamp(30rem, 44vw, 46rem)',
          maxWidth: '94vw',
          background: 'var(--col-bg)',
          border: '1px solid var(--col-border)',
          borderRadius: 10,
          boxShadow: '0 30px 60px rgba(0,0,0,.4)',
          padding: '1.75rem',
        }}
      >
        <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--ink)', marginBottom: '.35rem' }}>
          Create a task
        </div>
        <div style={{ fontSize: '.85rem', color: 'var(--ink-soft)', marginBottom: '1.25rem' }}>
          How would you like to create it?
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '.75rem' }}>
          {onAgentMode && (
            <button
              type="button"
              onClick={onAgentMode}
              style={chooserCard}
              onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'var(--accent)')}
              onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'var(--col-border)')}
            >
              <div style={{ fontSize: '1.4rem', lineHeight: 1 }}>✨</div>
              <div style={{ minWidth: 0 }}>
                <div style={chooserCardTitle}>
                  Let an AI draft it <span style={{ color: 'var(--accent)', fontWeight: 600 }}>· recommended</span>
                </div>
                <div style={chooserCardDesc}>
                  Describe your goal in plain English — an assistant reads your project and fills in the task for you.
                </div>
              </div>
            </button>
          )}
          <button
            type="button"
            onClick={onManual}
            style={chooserCard}
            onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'var(--accent)')}
            onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'var(--col-border)')}
          >
            <div style={{ fontSize: '1.4rem', lineHeight: 1 }}>✍️</div>
            <div style={{ minWidth: 0 }}>
              <div style={chooserCardTitle}>Fill it in myself</div>
              <div style={chooserCardDesc}>Set the title, lane, and details yourself.</div>
            </div>
          </button>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1.25rem' }}>
          <button type="button" onClick={onClose} style={chooserCancel}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
