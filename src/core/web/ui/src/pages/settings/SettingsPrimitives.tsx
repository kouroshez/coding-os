// Form primitives shared by every settings section.

import type * as React from "react";

export function EnvBadge({ varName, value }: { varName: string; value: string }) {
  return (
    <span
      className="ml-2 rounded border border-[var(--cos-warn)] bg-[var(--cos-warn-tint)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--cos-warn)]"
      title={`Overridden by env var: ${varName}=${value}`}
    >
      env: {varName}={value}
    </span>
  );
}

export function SectionHeader({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="mb-4">
      <h2 className="text-sm font-semibold text-[var(--cos-text)]">{title}</h2>
      <p className="mt-0.5 text-xs text-[var(--cos-muted)]">{desc}</p>
    </div>
  );
}

export function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-3 py-2">
      <span className="w-44 shrink-0 text-xs text-[var(--cos-muted)]">{label}</span>
      <div className="flex flex-1 flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

export function NumInput({
  value,
  onChange,
  min,
  max,
  step,
  disabled,
}: {
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
}) {
  return (
    <input
      type="number"
      value={value}
      min={min}
      max={max}
      step={step ?? 1}
      disabled={disabled}
      onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
      className={[
        "w-28 rounded border border-[var(--cos-border)] bg-[var(--cos-bg)]",
        "px-2 py-1 font-mono text-xs text-[var(--cos-text)]",
        "focus:outline-none focus:ring-1 focus:ring-[var(--accent)]",
        disabled ? "cursor-not-allowed opacity-50" : "",
      ].join(" ")}
    />
  );
}

export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <span className="flex min-w-0 items-center gap-2 text-xs">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        className={[
          "relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full",
          "border transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
          // The TRACK carries the state and the knob stays a constant light
          // puck. Tinting the knob instead made "off" (a dark dot on a pale
          // track) read as filled and "on" as empty — the state inverted.
          checked
            ? "border-[var(--accent)] bg-[var(--accent)]"
            : "border-[var(--cos-border)] bg-[var(--cos-muted)]/40",
        ].join(" ")}
      >
        <span
          aria-hidden
          className={[
            "pointer-events-none absolute left-0.5 h-3.5 w-3.5 rounded-full",
            "bg-white shadow-sm transition-transform",
            checked ? "translate-x-4" : "translate-x-0",
          ].join(" ")}
        />
      </button>
      <span className="truncate text-[var(--cos-text)]">{label}</span>
    </span>
  );
}
