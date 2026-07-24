import { type CSSProperties } from 'react';
import type { SwimlaneDTO } from './types';

export interface TaskEditFormState {
  title: string;
  priority: string;
  swimlane: string;
  appetite: string;
  labels: string;
  body: string;
}

export function TaskEditForm({
  form,
  setForm,
  swimlanes,
  saving,
  error,
}: {
  form: TaskEditFormState;
  setForm: (value: TaskEditFormState | null) => void;
  swimlanes: SwimlaneDTO[];
  saving: boolean;
  error: string | null;
}) {
  const mono = "'JetBrains Mono', monospace";
  const set = (k: keyof TaskEditFormState, v: string) => setForm({ ...form, [k]: v });
  const inputStyle: CSSProperties = {
    width: '100%',
    background: 'var(--board-grain)',
    border: '1px solid var(--col-border)',
    color: 'var(--ink)',
    fontFamily: mono,
    fontSize: 12,
    padding: '6px 8px',
    borderRadius: 3,
  };
  const labelStyle: CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    fontFamily: mono,
    fontSize: 10.5,
    color: 'var(--ink-faint)',
    letterSpacing: '.04em',
  };
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {error && <div style={{ color: '#dc2626', fontFamily: mono, fontSize: 12 }}>{error}</div>}
      <label style={labelStyle}>
        TITLE
        <input
          value={form.title}
          disabled={saving}
          onChange={(e) => set('title', e.target.value)}
          style={inputStyle}
        />
      </label>
      <div style={{ display: 'flex', gap: 12 }}>
        <label style={{ ...labelStyle, flex: 1 }}>
          PRIORITY
          <select
            value={form.priority}
            disabled={saving}
            onChange={(e) => set('priority', e.target.value)}
            style={inputStyle}
          >
            {['P0', 'P1', 'P2', 'P3'].map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label style={{ ...labelStyle, flex: 2 }}>
          SWIMLANE
          <select
            value={form.swimlane}
            disabled={saving}
            onChange={(e) => set('swimlane', e.target.value)}
            style={inputStyle}
          >
            {swimlanes.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label ?? s.id}
              </option>
            ))}
          </select>
        </label>
        <label style={{ ...labelStyle, flex: 1 }}>
          APPETITE
          <input
            value={form.appetite}
            disabled={saving}
            onChange={(e) => set('appetite', e.target.value)}
            style={inputStyle}
          />
        </label>
      </div>
      <label style={labelStyle}>
        LABELS (comma-separated)
        <input
          value={form.labels}
          disabled={saving}
          onChange={(e) => set('labels', e.target.value)}
          style={inputStyle}
        />
      </label>
      <label style={labelStyle}>
        BODY (markdown)
        <textarea
          value={form.body}
          disabled={saving}
          onChange={(e) => set('body', e.target.value)}
          rows={22}
          style={{ ...inputStyle, resize: 'vertical', lineHeight: 1.5 }}
        />
      </label>
    </div>
  );
}
