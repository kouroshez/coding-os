import { useEffect } from 'react';
import NewChatForm from '@/features/cognition/NewChatForm';

export function AgentTaskModal({
  open,
  onClose,
  onDone,
}: {
  open: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  // ESC / overlay click closes and refreshes the board so a just-drafted task
  // appears. The draft itself is owned by the shared chat composer below.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onDone();
        onClose();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onDone, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Draft a task with AI"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 200,
        background: 'rgba(0,0,0,.45)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 20,
      }}
      onClick={() => {
        onDone();
        onClose();
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          // Fluid: rem responds to browser zoom, vw grows on 4K, capped so a
          // single-prompt dialog never sprawls; maxWidth lets it use the screen.
          width: 'clamp(34rem, 52vw, 60rem)',
          maxWidth: '94vw',
          maxHeight: '90vh',
          overflowY: 'auto',
          background: 'var(--col-bg)',
          border: '1px solid var(--col-border)',
          borderRadius: 10,
          boxShadow: '0 30px 60px rgba(0,0,0,.4)',
          padding: '20px 22px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12 }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink)' }}>✨ Draft with AI</div>
          <button
            type="button"
            onClick={() => {
              onDone();
              onClose();
            }}
            aria-label="Close"
            style={{
              background: 'transparent',
              border: '1px solid var(--col-border)',
              borderRadius: 6,
              color: 'var(--ink-soft)',
              fontSize: 11,
              padding: '3px 9px',
              cursor: 'pointer',
            }}
          >
            esc
          </button>
        </div>
        <div
          style={{
            fontSize: '.82rem',
            color: 'var(--ink-soft)',
            margin: '6px 0 16px',
            lineHeight: 1.5,
          }}
        >
          Describe what you want in plain English — the assistant reads your project and writes the task for
          you. This is the same chat used everywhere else in the Hub.
        </div>
        {/* The ONE global chat composer + live stream (NewChatForm), pointed at
            the task-authoring endpoint. One chat surface, edited in one place. */}
        <NewChatForm endpoint="/api/cognition/author-task" onComplete={() => onDone()} />
      </div>
    </div>
  );
}
