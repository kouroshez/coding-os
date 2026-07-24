import type { ReactNode } from 'react';

export function FormField({
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

export function ChipRow({
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
