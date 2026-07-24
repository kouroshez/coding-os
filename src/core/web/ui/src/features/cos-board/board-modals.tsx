import { useEffect, useState, type CSSProperties, type ReactNode } from 'react';
import NewChatForm from '@/features/cognition/NewChatForm';
import { alpha, lanePalette, priorityStyle } from './board-shared';
import type { CreateTaskForm } from './board-shared';
import { KIND_COLORS, kindStyle } from './kindColors';
import type { SwimlaneDTO } from './types';

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

export function CreateTaskModal({
  open,
  onClose,
  nextId,
  swimlanes,
  onCreate,
  onAgentMode,
}: {
  open: boolean;
  onClose: () => void;
  nextId: number;
  swimlanes: SwimlaneDTO[];
  onCreate: (form: CreateTaskForm) => Promise<void>;
  onAgentMode?: () => void;
}) {
  const [form, setForm] = useState<{
    title: string;
    swimlane: string;
    kind: string;
    priority: string;
    appetite: string;
    epic: string;
    labels: string;
    outcome: string;
  }>({
    title: '',
    swimlane: '',
    kind: 'feature',
    priority: 'P2',
    appetite: '1d',
    epic: '',
    labels: '',
    outcome: '',
  });
  // Step 1 is always the mode chooser (agent vs manual); the form is step 2.
  const [mode, setMode] = useState<'choose' | 'manual'>('choose');

  useEffect(() => {
    if (open) {
      setForm({
        title: '',
        swimlane: swimlanes[0]?.id || '',
        kind: 'feature',
        priority: 'P2',
        appetite: '1d',
        epic: '',
        labels: '',
        outcome: '',
      });
      setMode('choose');
    }
  }, [open, swimlanes]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  // Step 1 — plain-language chooser so a non-developer sees the agent path
  // up front (it used to be a tiny ghost button almost nobody noticed).
  if (mode === 'choose') {
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
              onClick={() => setMode('manual')}
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

  const kindOpts = Object.entries(KIND_COLORS).map(([k, v]) => ({
    value: k,
    label: v.label,
    color: v.chip,
  }));
  const priorityOpts = [
    { value: 'P0', label: 'P0', color: 'var(--cos-err)' },
    { value: 'P1', label: 'P1', color: 'var(--cos-warn)' },
    { value: 'P2', label: 'P2', color: 'var(--cos-muted)' },
    { value: 'P3', label: 'P3', color: 'var(--cos-faint)' },
  ];
  const previewKind = kindStyle(form.kind);
  const previewLane = swimlanes.find((l) => l.id === form.swimlane);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="New task"
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
      onClick={onClose}
    >
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={async (e) => {
          e.preventDefault();
          if (!form.title.trim() || !form.swimlane) return;
          await onCreate({
            title: form.title.trim(),
            swimlane: form.swimlane,
            kind: form.kind,
            priority: form.priority,
            appetite: form.appetite,
            epic: form.epic || null,
            labels: form.labels.split(',').map((s) => s.trim()).filter(Boolean),
            outcome: form.outcome || null,
          });
        }}
        style={{
          // Fluid: grows with screen + browser zoom, capped so the form stays
          // readable; the side preview column scales instead of a fixed 240px.
          width: 'clamp(40rem, 62vw, 80rem)',
          maxWidth: '94vw',
          maxHeight: '90vh',
          overflowY: 'auto',
          background: 'var(--col-bg)',
          border: '1px solid var(--col-border)',
          borderRadius: 6,
          boxShadow: '0 30px 60px rgba(0,0,0,.4)',
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr) clamp(14rem, 18vw, 22rem)',
        }}
      >
        <div style={{ padding: '20px 22px', borderRight: '1px solid var(--col-border)' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'baseline',
              gap: 10,
              marginBottom: 18,
              paddingBottom: 10,
              borderBottom: '2px dashed var(--col-border)',
            }}
          >
            <button
              type="button"
              onClick={() => setMode('choose')}
              title="Back to the create options"
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--ink-soft)',
                cursor: 'pointer',
                fontSize: '.8rem',
                padding: 0,
              }}
            >
              ‹ back
            </button>
            <div style={{ fontSize: 22, fontWeight: 700, letterSpacing: '.02em', color: 'var(--ink)' }}>
              New task
            </div>
            <div style={{ fontSize: '.72rem', color: 'var(--ink-faint)', marginLeft: 'auto' }}>
              #{String(nextId).padStart(3, '0')}
            </div>
          </div>

          <FormField label="Title" required>
            <input
              autoFocus
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              placeholder="Implement Kuzu backend"
              maxLength={80}
              style={formInput}
            />
          </FormField>

          <FormField label="Swimlane" required>
            <ChipRow
              options={swimlanes.map((s) => ({ value: s.id, label: s.label, color: s.accent }))}
              value={form.swimlane}
              onChange={(v) => setForm((f) => ({ ...f, swimlane: v }))}
            />
          </FormField>

          <details style={{ marginTop: 4 }}>
            <summary
              style={{
                cursor: 'pointer',
                fontSize: '.78rem',
                color: 'var(--ink-soft)',
                userSelect: 'none',
                padding: '.4rem 0',
              }}
            >
              More options
            </summary>
            <div style={{ marginTop: 8 }}>
              <FormField label="Kind">
                <ChipRow options={kindOpts} value={form.kind} onChange={(v) => setForm((f) => ({ ...f, kind: v }))} />
              </FormField>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                <FormField label="Priority">
                  <ChipRow options={priorityOpts} value={form.priority} onChange={(v) => setForm((f) => ({ ...f, priority: v }))} />
                </FormField>
                <FormField label="Estimated effort" hint="30m 2h 1d 3d 1w">
                  <input
                    value={form.appetite}
                    onChange={(e) => setForm((f) => ({ ...f, appetite: e.target.value }))}
                    style={monoFormInput}
                  />
                </FormField>
              </div>

              <FormField label="Labels" hint="comma-separated">
                <input
                  value={form.labels}
                  onChange={(e) => setForm((f) => ({ ...f, labels: e.target.value }))}
                  placeholder="indexing, perf"
                  style={monoFormInput}
                />
              </FormField>

              <FormField label="What does done look like?" hint="optional">
                <textarea
                  value={form.outcome}
                  onChange={(e) => setForm((f) => ({ ...f, outcome: e.target.value }))}
                  rows={2}
                  style={{ ...formInput, resize: 'vertical' }}
                />
              </FormField>
            </div>
          </details>

          <div
            style={{
              display: 'flex',
              gap: 10,
              justifyContent: 'flex-end',
              marginTop: 14,
              paddingTop: 14,
              borderTop: '1px dashed var(--col-border)',
            }}
          >
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: '8px 14px',
                fontSize: 12,
                fontFamily: "'JetBrains Mono', monospace",
                fontWeight: 600,
                background: 'transparent',
                color: 'var(--ink-soft)',
                border: '1.5px solid var(--col-border)',
                borderRadius: 3,
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!form.title.trim() || !form.swimlane}
              title={!form.title.trim() ? 'Add a title first' : !form.swimlane ? 'Pick a lane first' : undefined}
              style={{
                padding: '8px 18px',
                fontSize: 12,
                fontFamily: "'JetBrains Mono', monospace",
                fontWeight: 700,
                background: 'var(--accent)',
                color: 'white',
                border: '1.5px solid var(--accent)',
                borderRadius: 3,
                cursor: !form.title.trim() || !form.swimlane ? 'not-allowed' : 'pointer',
                opacity: !form.title.trim() || !form.swimlane ? 0.45 : 1,
                letterSpacing: '.02em',
              }}
            >
              Create task ▸
            </button>
          </div>
        </div>

        <div
          style={{
            padding: '20px 18px',
            background: 'var(--board)',
            borderRadius: '0 6px 6px 0',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 10,
              fontWeight: 600,
              color: 'var(--ink-soft)',
              letterSpacing: '.04em',
              textTransform: 'uppercase',
              marginBottom: 10,
            }}
          >
            preview
          </div>
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div
              style={{
                width: 200,
                padding: '10px 11px 9px',
                fontFamily: 'inherit',
                fontSize: 14,
                lineHeight: 1.25,
                color: 'var(--cos-text)',
                background: previewLane
                  ? `linear-gradient(155deg, ${alpha(previewLane.color, 0.16)} 0%, ${alpha(previewLane.color, 0.07)} 100%)`
                  : 'linear-gradient(155deg, var(--cos-raised) 0%, var(--cos-panel) 100%)',
                borderRadius: '8px',
                transform: 'none',
                boxShadow: '0 4px 8px rgba(0,0,0,.15), 0 10px 20px -6px rgba(0,0,0,.2)',
                borderLeft: `5px solid ${previewLane ? lanePalette(previewLane).accent : '#888'}`,
                ...priorityStyle(form.priority),
              }}
            >
              <div style={{ display: 'flex', gap: 6, marginBottom: 4, alignItems: 'center' }}>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, fontWeight: 700 }}>
                  TASK-{String(nextId).padStart(3, '0')}
                </span>
                <span
                  style={{
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: 9,
                    fontWeight: 700,
                    color: '#fff',
                    background: previewKind.chip,
                    padding: '1px 5px',
                    borderRadius: 2,
                    textTransform: 'uppercase',
                  }}
                >
                  {previewKind.label}
                </span>
              </div>
              <div style={{ fontWeight: 700, fontSize: 15 }}>
                {form.title || <span style={{ color: '#9a948a', fontStyle: 'italic' }}>(title…)</span>}
              </div>
            </div>
          </div>
          <div
            style={{
              fontSize: '.72rem',
              color: 'var(--ink-faint)',
              marginTop: 12,
              lineHeight: 1.6,
            }}
          >
            Saved as <b>Task #{String(nextId).padStart(3, '0')}</b> in the{' '}
            <b style={{ color: previewLane?.accent }}>{previewLane?.label || form.swimlane || '…'}</b> lane.
          </div>
        </div>
      </form>
    </div>
  );
}

const formInput: CSSProperties = {
  width: '100%',
  padding: '8px 10px',
  fontFamily: 'inherit',
  fontSize: 15,
  background: 'var(--board)',
  color: 'var(--ink)',
  border: '1.5px solid var(--col-border)',
  borderRadius: 3,
  outline: 'none',
};
const monoFormInput: CSSProperties = {
  ...formInput,
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: 12,
};

function FormField({
  label,
  hint,
  required,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <label style={{ display: 'block', marginBottom: 12 }}>
      <div
        style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 10,
          fontWeight: 600,
          color: 'var(--ink-soft)',
          letterSpacing: '.04em',
          textTransform: 'uppercase',
          marginBottom: 4,
        }}
      >
        {label}
        {required && <span style={{ color: '#c0392b' }}> *</span>}
        {hint && (
          <span style={{ color: 'var(--ink-faint)', fontWeight: 400, textTransform: 'none', marginLeft: 6 }}>
            — {hint}
          </span>
        )}
      </div>
      {children}
    </label>
  );
}

function ChipRow({
  options,
  value,
  onChange,
}: {
  options: { value: string; label: string; color?: string }[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          style={{
            padding: '5px 9px',
            fontSize: 11,
            fontFamily: "'JetBrains Mono', monospace",
            fontWeight: 600,
            background: value === o.value ? o.color || 'var(--accent)' : 'transparent',
            color: value === o.value ? 'white' : 'var(--ink-soft)',
            border: `1.5px solid ${value === o.value ? o.color || 'var(--accent)' : 'var(--col-border)'}`,
            borderRadius: 3,
            cursor: 'pointer',
            transition: 'all .12s ease',
          }}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
