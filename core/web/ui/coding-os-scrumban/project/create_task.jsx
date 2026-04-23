// Create task modal — mirrors cos_task_create MCP signature
const { useState: useStateC, useEffect: useEffectC, useRef: useRefC } = React;

function Field({ label, hint, children, required }) {
  return (
    <label style={{ display: 'block', marginBottom: 12 }}>
      <div style={{
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 10, fontWeight: 600,
        color: 'var(--ink-soft)',
        letterSpacing: '.04em', textTransform: 'uppercase',
        marginBottom: 4,
      }}>
        {label}{required && <span style={{ color: 'var(--red)' }}> *</span>}
        {hint && <span style={{ color: 'var(--ink-faint)', fontWeight: 400, textTransform: 'none', marginLeft: 6 }}>— {hint}</span>}
      </div>
      {children}
    </label>
  );
}

const inputStyle = {
  width: '100%', padding: '8px 10px',
  fontFamily: "'Kalam', cursive", fontSize: 15,
  background: 'var(--board)',
  color: 'var(--ink)',
  border: '1.5px solid var(--col-border)',
  borderRadius: 3,
  outline: 'none',
};
const monoInput = {
  ...inputStyle,
  fontFamily: 'JetBrains Mono, monospace', fontSize: 12,
};

function ChipRow({ options, value, onChange, renderChip }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
      {options.map(o => (
        <button key={o.value} type="button" onClick={() => onChange(o.value)} style={{
          padding: '5px 9px', fontSize: 11,
          fontFamily: 'JetBrains Mono, monospace', fontWeight: 600,
          background: value === o.value ? (o.color || 'var(--accent)') : 'transparent',
          color: value === o.value ? 'white' : 'var(--ink-soft)',
          border: `1.5px solid ${value === o.value ? (o.color || 'var(--accent)') : 'var(--col-border)'}`,
          borderRadius: 3, cursor: 'pointer',
          transition: 'all .12s ease',
        }}>{renderChip ? renderChip(o) : o.label}</button>
      ))}
    </div>
  );
}

function CreateTaskModal({ open, onClose, onCreate, nextId }) {
  const [form, setForm] = useStateC({
    title: '', swimlane: 'board-os', kind: 'feature',
    priority: 'P2', appetite: '1d', epic: '',
    labels: '', status: 'icebox',
    outcome: '',
  });
  const [errors, setErrors] = useStateC({});
  const titleRef = useRefC(null);

  useEffectC(() => {
    if (open) {
      setForm({
        title: '', swimlane: 'board-os', kind: 'feature',
        priority: 'P2', appetite: '1d', epic: '',
        labels: '', status: 'icebox', outcome: '',
      });
      setErrors({});
      setTimeout(() => titleRef.current?.focus(), 50);
    }
  }, [open]);

  useEffectC(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const appetitePresets = ['30m', '2h', '4h', '1d', '3d', '1w', '1cy'];
  const appetiteRegex = /^\d+[mhdwcy]$|^\d+cy$/;

  const validate = () => {
    const e = {};
    if (!form.title.trim()) e.title = 'required';
    else if (form.title.length > 80) e.title = 'max 80 chars';
    if (!appetiteRegex.test(form.appetite)) e.appetite = 'format: 30m, 2h, 1d, 3d, 1w, 1cy';
    if (form.epic && !/^[a-z0-9-]+$/.test(form.epic)) e.epic = 'lowercase, digits, hyphens';
    const labels = form.labels.split(',').map(s => s.trim()).filter(Boolean);
    if (labels.some(l => !/^[a-z0-9-]+$/.test(l))) e.labels = 'lowercase, digits, hyphens';
    if (labels.some(l => Object.keys(window.KIND_COLORS).includes(l))) e.labels = 'labels cannot be kind values';
    return e;
  };

  const submit = (e) => {
    e.preventDefault();
    const errs = validate();
    setErrors(errs);
    if (Object.keys(errs).length) return;

    const labels = form.labels.split(',').map(s => s.trim()).filter(Boolean);
    const task = {
      id: `TASK-${String(nextId).padStart(3, '0')}`,
      title: form.title.trim(),
      swimlane: form.swimlane,
      kind: form.kind,
      status: form.status,
      priority: form.priority,
      appetite: form.appetite,
      epic: form.epic.trim() || null,
      labels,
      agent: null,
      started: form.status === 'in_progress' ? new Date().toISOString().slice(0, 10) : null,
      workLog: form.outcome.trim() ? [
        `${new Date().toISOString().slice(0, 10)} [human | local-mac]: created — ${form.outcome.trim().slice(0, 110)}`,
      ] : [],
      blockedReason: null,
      stale: false,
      rotation: Math.random() * 3 - 1.5,
      depends: [],
    };
    onCreate(task);
    onClose();
  };

  const kindOpts = Object.entries(window.KIND_COLORS).map(([k, v]) => ({
    value: k, label: v.label, color: v.chip,
  }));
  const priorityOpts = [
    { value: 'P0', label: 'P0', color: '#c0392b' },
    { value: 'P1', label: 'P1', color: '#ea580c' },
    { value: 'P2', label: 'P2', color: '#6b665e' },
    { value: 'P3', label: 'P3', color: '#b8b0a3' },
  ];
  const statusOpts = [
    { value: 'icebox',      label: 'icebox',      color: '#6b7280' },
    { value: 'ready',       label: 'ready',       color: '#16a34a' },
    { value: 'emergency',   label: 'emergency',   color: '#c0392b' },
    { value: 'in_progress', label: 'in_progress', color: '#d97706' },
  ];
  const swimOpts = window.SWIMLANES.map(l => ({ value: l.id, label: l.label, color: l.accent }));
  const epicOpts = [{ value: '', label: 'none', color: '#9ca3af' }, ...window.EPICS.map(e => ({ value: e.id, label: e.id, color: '#4f46e5' }))];

  const previewKind = window.KIND_COLORS[form.kind];
  const previewLane = window.SWIMLANES.find(l => l.id === form.swimlane);

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 200,
      background: 'rgba(0,0,0,.45)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 20,
      animation: 'fadeIn .15s ease',
    }} onClick={onClose}>
      <form onSubmit={submit} onClick={e => e.stopPropagation()} style={{
        width: 720, maxWidth: '100%', maxHeight: '90vh', overflowY: 'auto',
        background: 'var(--col-bg)',
        border: '1px solid var(--col-border)',
        borderRadius: 6,
        boxShadow: '0 30px 60px rgba(0,0,0,.4)',
        display: 'grid',
        gridTemplateColumns: '1fr 260px',
      }}>
        {/* LEFT — form */}
        <div style={{ padding: '20px 22px', borderRight: '1px solid var(--col-border)' }}>
          <div style={{
            display: 'flex', alignItems: 'baseline', gap: 10,
            marginBottom: 18, paddingBottom: 10,
            borderBottom: '2px dashed var(--col-border)',
          }}>
            <div style={{
              fontFamily: "'Permanent Marker', cursive",
              fontSize: 22, letterSpacing: '.02em',
              color: 'var(--accent)',
            }}>new task</div>
            <div style={{
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: 11, color: 'var(--ink-faint)',
            }}>cos_task_create → TASK-{String(nextId).padStart(3, '0')}</div>
          </div>

          <Field label="Title" required hint="≤80 chars, one-line outcome">
            <input
              ref={titleRef}
              type="text" value={form.title}
              onChange={e => set('title', e.target.value)}
              placeholder="Implement Kuzu backend"
              maxLength={80}
              style={{ ...inputStyle, borderColor: errors.title ? 'var(--red)' : 'var(--col-border)' }}
            />
            {errors.title && <div style={{ fontSize: 10, color: 'var(--red)', marginTop: 3, fontFamily: 'JetBrains Mono, monospace' }}>{errors.title}</div>}
          </Field>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Field label="Swimlane" required hint="domain">
              <ChipRow options={swimOpts} value={form.swimlane} onChange={v => set('swimlane', v)} />
            </Field>
          </div>

          <Field label="Kind" required hint="closed enum — colour stability">
            <ChipRow options={kindOpts} value={form.kind} onChange={v => set('kind', v)} />
          </Field>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <Field label="Priority" required>
              <ChipRow options={priorityOpts} value={form.priority} onChange={v => set('priority', v)} />
            </Field>
            <Field label="Appetite" required hint="shape-up style">
              <input
                type="text" value={form.appetite}
                onChange={e => set('appetite', e.target.value)}
                placeholder="1d"
                style={{ ...monoInput, borderColor: errors.appetite ? 'var(--red)' : 'var(--col-border)' }}
              />
              <div style={{ display: 'flex', gap: 4, marginTop: 5, flexWrap: 'wrap' }}>
                {appetitePresets.map(p => (
                  <button key={p} type="button" onClick={() => set('appetite', p)} style={{
                    padding: '2px 6px', fontSize: 10,
                    fontFamily: 'JetBrains Mono, monospace',
                    background: form.appetite === p ? 'var(--accent)' : 'transparent',
                    color: form.appetite === p ? 'white' : 'var(--ink-soft)',
                    border: '1px solid var(--col-border)', borderRadius: 2,
                    cursor: 'pointer',
                  }}>{p}</button>
                ))}
              </div>
              {errors.appetite && <div style={{ fontSize: 10, color: 'var(--red)', marginTop: 3, fontFamily: 'JetBrains Mono, monospace' }}>{errors.appetite}</div>}
            </Field>
          </div>

          <Field label="Epic" hint="initiative — optional">
            <ChipRow options={epicOpts} value={form.epic} onChange={v => set('epic', v)} />
          </Field>

          <Field label="Labels" hint="comma-separated, free tags">
            <input
              type="text" value={form.labels}
              onChange={e => set('labels', e.target.value)}
              placeholder="indexing, perf"
              style={{ ...monoInput, borderColor: errors.labels ? 'var(--red)' : 'var(--col-border)' }}
            />
            {errors.labels && <div style={{ fontSize: 10, color: 'var(--red)', marginTop: 3, fontFamily: 'JetBrains Mono, monospace' }}>{errors.labels}</div>}
          </Field>

          <Field label="Initial status" hint="WIP caps still apply on in_progress">
            <ChipRow options={statusOpts} value={form.status} onChange={v => set('status', v)} />
          </Field>

          <Field label="Outcome / first work-log line" hint="optional — one sentence G/W/T target">
            <textarea
              value={form.outcome}
              onChange={e => set('outcome', e.target.value)}
              placeholder="SQLite fallback swappable with Kuzu via config; all 50 parity tests pass."
              rows={2}
              style={{ ...inputStyle, resize: 'vertical', fontFamily: "'Kalam', cursive" }}
            />
          </Field>

          <div style={{
            display: 'flex', gap: 10, justifyContent: 'space-between',
            marginTop: 14, paddingTop: 14,
            borderTop: '1px dashed var(--col-border)',
          }}>
            <div style={{
              fontFamily: 'JetBrains Mono, monospace', fontSize: 10,
              color: 'var(--ink-faint)', alignSelf: 'center',
            }}>
              ⏎ submit · esc cancel · hook: validate-task-frontmatter.sh
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="button" onClick={onClose} style={{
                padding: '8px 14px', fontSize: 12,
                fontFamily: 'JetBrains Mono, monospace', fontWeight: 600,
                background: 'transparent', color: 'var(--ink-soft)',
                border: '1.5px solid var(--col-border)',
                borderRadius: 3, cursor: 'pointer',
              }}>cancel</button>
              <button type="submit" style={{
                padding: '8px 18px', fontSize: 12,
                fontFamily: 'JetBrains Mono, monospace', fontWeight: 700,
                background: 'var(--accent)', color: 'white',
                border: '1.5px solid var(--accent)',
                borderRadius: 3, cursor: 'pointer',
                letterSpacing: '.02em',
              }}>create ▸</button>
            </div>
          </div>
        </div>

        {/* RIGHT — live card preview */}
        <div style={{
          padding: '20px 18px',
          background: 'var(--board)',
          borderRadius: '0 6px 6px 0',
          display: 'flex', flexDirection: 'column',
        }}>
          <div style={{
            fontFamily: 'JetBrains Mono, monospace', fontSize: 10, fontWeight: 600,
            color: 'var(--ink-soft)', letterSpacing: '.04em',
            textTransform: 'uppercase', marginBottom: 10,
          }}>preview</div>

          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{
              width: 220,
              padding: '10px 11px 9px',
              fontFamily: "'Kalam', cursive",
              fontSize: 14, lineHeight: 1.25, color: '#1a1814',
              background: `linear-gradient(155deg, ${previewKind.bg} 0%, ${previewKind.bg2} 100%)`,
              borderRadius: '2px 3px 2px 3px',
              transform: 'rotate(-1.2deg)',
              boxShadow: '0 4px 8px rgba(0,0,0,.15), 0 10px 20px -6px rgba(0,0,0,.2)',
              borderLeft: `5px solid ${previewLane?.accent || '#888'}`,
              ...(form.priority === 'P0' ? { outline: '2.5px double #c0392b', outlineOffset: 1 } :
                  form.priority === 'P1' ? { outline: '1.5px solid #ea580c' } :
                  form.priority === 'P2' ? { outline: '1px dashed #8a8378' } :
                                            { outline: '1px dotted #b8b0a3' }),
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, fontWeight: 700, color: '#3a3530' }}>
                  TASK-{String(nextId).padStart(3, '0')}
                </span>
                <span style={{
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: 9, fontWeight: 700, color: '#fff',
                  background: previewKind.chip, padding: '1px 5px', borderRadius: 2,
                  letterSpacing: '.04em', textTransform: 'uppercase',
                }}>{previewKind.label}</span>
                <span style={{
                  fontFamily: 'JetBrains Mono, monospace', fontSize: 9, fontWeight: 700,
                  color: form.priority === 'P0' ? '#b91c1c' : form.priority === 'P1' ? '#c2410c' : '#6b665e',
                }}>{form.priority}</span>
              </div>
              <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 6 }}>
                {form.title || <span style={{ color: '#9a948a', fontStyle: 'italic' }}>(title…)</span>}
              </div>
              <div style={{
                display: 'flex', flexWrap: 'wrap', gap: 4,
                fontFamily: 'JetBrains Mono, monospace', fontSize: 9, color: '#4a4540',
              }}>
                <span style={{ background: 'rgba(0,0,0,.06)', padding: '1px 5px', borderRadius: 2 }}>◷ {form.appetite}</span>
                {form.epic && (
                  <span style={{ background: 'rgba(0,0,0,.08)', padding: '1px 5px', borderRadius: 2, fontWeight: 600 }}>
                    #{form.epic}
                  </span>
                )}
                {form.labels.split(',').map(s => s.trim()).filter(Boolean).slice(0, 3).map(l => (
                  <span key={l} style={{ color: '#6b665e' }}>·{l}</span>
                ))}
              </div>
            </div>
          </div>

          <div style={{
            fontFamily: 'JetBrains Mono, monospace', fontSize: 10,
            color: 'var(--ink-faint)', marginTop: 12,
            lineHeight: 1.5,
          }}>
            <div>→ docs/tasks/TASK-{String(nextId).padStart(3, '0')}-{(form.title || 'untitled').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 30)}.md</div>
            <div style={{ marginTop: 4 }}>→ lane <span style={{ color: previewLane?.accent, fontWeight: 700 }}>{form.swimlane}</span> → col <span style={{ color: 'var(--accent)', fontWeight: 700 }}>{form.status}</span></div>
          </div>
        </div>
      </form>
    </div>
  );
}

window.CreateTaskModal = CreateTaskModal;
