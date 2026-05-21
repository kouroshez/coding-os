/**
 * Shared visual primitives for Hub pages.
 *
 * PURPOSE: Keep every page header / action bar / banner / skeleton /
 *          empty state visually consistent. Move shared components
 *          here once instead of copy-pasting Tailwind classes into
 *          ten files.
 * INPUT:   React render props (label, onClick, icon, kind, children).
 * OUTPUT:  Styled JSX — no business logic, no data fetching.
 * NOTES:   All design tokens come from cos-board-tokens.css. Icons are
 *          inline SVG (no extra deps).
 */

import type React from 'react';

// --------------------------------------------------------------------------
// PageHeader — hero block with gradient backdrop, title, subtitle, pill.
// --------------------------------------------------------------------------

export function PageHeader({
  eyebrow,
  title,
  subtitle,
  right,
  actions,
}: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  right?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <header className="mb-8 relative">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 -top-6 -z-10 h-[260px]"
        style={{
          background:
            'radial-gradient(55% 90% at 25% 0%, color-mix(in oklab, var(--accent) 14%, transparent), transparent 70%), radial-gradient(40% 70% at 90% 10%, color-mix(in oklab, var(--cos-accent, var(--accent)) 10%, transparent), transparent 70%)',
        }}
      />
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div className="min-w-0">
          {eyebrow && (
            <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-[var(--cos-border)] bg-[var(--cos-panel)]/60 px-3 py-1 text-[10px] font-mono uppercase tracking-[0.18em] text-[var(--cos-muted)] backdrop-blur">
              {eyebrow}
            </div>
          )}
          <h1 className="bg-gradient-to-br from-[var(--cos-text)] via-[var(--cos-text)] to-[color-mix(in_oklab,var(--accent)_60%,var(--cos-text))] bg-clip-text text-3xl font-bold tracking-tight text-transparent sm:text-4xl">
            {title}
          </h1>
          {subtitle && (
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-[var(--cos-muted)]">
              {subtitle}
            </p>
          )}
        </div>
        {right}
      </div>
      {actions && <div className="mt-6 flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

// --------------------------------------------------------------------------
// StatusPill — small "live · port 9188" badge with optional dot.
// --------------------------------------------------------------------------

export function StatusPill({
  label, dotColor = 'bg-emerald-400',
}: { label: string; dotColor?: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className={`h-1.5 w-1.5 rounded-full ${dotColor} shadow-[0_0_8px] shadow-current/60`} />
      {label}
    </span>
  );
}

// --------------------------------------------------------------------------
// ActionPill — rounded-full action button, icon + label.
// --------------------------------------------------------------------------

export function ActionPill({
  icon, label, onClick, disabled, primary,
}: {
  icon?: React.ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  primary?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={[
        'group inline-flex items-center gap-2 rounded-full border px-4 py-2 text-xs font-medium transition-all duration-150',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--cos-bg)]',
        primary
          ? 'border-transparent bg-[var(--accent)] text-[var(--cos-bg)] shadow-lg shadow-[var(--accent)]/20 hover:shadow-[var(--accent)]/40 hover:-translate-y-px'
          : 'border-[var(--cos-border)] bg-[var(--cos-panel)]/70 text-[var(--cos-text)] backdrop-blur hover:border-[var(--accent)] hover:bg-[var(--cos-panel)] hover:text-[var(--accent)]',
        disabled ? 'cursor-not-allowed opacity-50 hover:translate-y-0' : '',
      ].join(' ')}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

// --------------------------------------------------------------------------
// Banner — dismissible ok/error notice.
// --------------------------------------------------------------------------

export function Banner({
  kind, children, onDismiss,
}: {
  kind: 'ok' | 'error' | 'info';
  children: React.ReactNode;
  onDismiss?: () => void;
}) {
  const palette = kind === 'ok'
    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
    : kind === 'error'
    ? 'border-rose-500/30 bg-rose-500/10 text-rose-200'
    : 'border-[var(--cos-border)] bg-[var(--cos-panel)]/70 text-[var(--cos-muted)]';
  return (
    <div className={`mb-5 flex items-start justify-between gap-3 rounded-xl border px-4 py-3 text-xs ${palette}`}>
      <span>{children}</span>
      {onDismiss && (
        <button
          type="button"
          className="shrink-0 text-[10px] uppercase tracking-wider opacity-70 hover:opacity-100"
          onClick={onDismiss}
        >
          dismiss
        </button>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------
// SkeletonGrid — placeholder cards while data loads.
// --------------------------------------------------------------------------

export function SkeletonGrid({ count = 3, height = 148 }: { count?: number; height?: number }) {
  return (
    <ul className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <li
          key={i}
          style={{ height }}
          className="animate-pulse rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/40"
        />
      ))}
    </ul>
  );
}

// --------------------------------------------------------------------------
// EmptyState — illustrated zero-data panel.
// --------------------------------------------------------------------------

export function EmptyState({
  icon, title, children,
}: {
  icon: React.ReactNode;
  title: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <div className="glass-card relative overflow-hidden rounded-3xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/60 p-12 backdrop-blur-xl shadow-xl transition-all duration-300 hover:shadow-2xl hover:shadow-[var(--accent)]/5">
      {/* Premium subtle glowing background vectors */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-20 -top-20 -z-10 h-72 w-72 rounded-full opacity-20 blur-[80px]"
        style={{
          background: 'radial-gradient(circle, var(--accent) 0%, transparent 70%)',
        }}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -left-20 -bottom-20 -z-10 h-72 w-72 rounded-full opacity-10 blur-[80px]"
        style={{
          background: 'radial-gradient(circle, var(--cos-accent, var(--accent)) 0%, transparent 70%)',
        }}
      />
      
      <div className="mx-auto max-w-lg text-center relative z-10">
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl border border-[var(--cos-border)] bg-gradient-to-br from-[var(--cos-panel)] to-[var(--cos-bg)] text-[var(--accent)] shadow-inner transition-transform duration-500 hover:rotate-12 hover:scale-105">
          {icon}
        </div>
        <h2 className="mb-3 text-xl font-bold tracking-tight text-[var(--cos-text)]">{title}</h2>
        {children && <div className="text-sm leading-relaxed text-[var(--cos-muted)]">{children}</div>}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// PageShell — consistent outer wrapper for every page.
// --------------------------------------------------------------------------

export function PageShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative flex h-full flex-col overflow-auto cos-scroll">
      <div className="mx-auto w-full max-w-7xl px-6 pb-12 pt-10 sm:px-10">{children}</div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Icons — inline SVG, no extra deps.
// --------------------------------------------------------------------------

const stroke = { strokeWidth: 1.6, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

export function Icon({ name, size = 14 }: { name: string; size?: number }) {
  const props = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', ...stroke };
  switch (name) {
    case 'plus':
      return <svg {...props}><path d="M12 5v14M5 12h14" /></svg>;
    case 'refresh':
      return <svg {...props}><path d="M3 12a9 9 0 0 1 15.5-6.3L21 8" /><path d="M21 4v4h-4" /><path d="M21 12a9 9 0 0 1-15.5 6.3L3 16" /><path d="M3 20v-4h4" /></svg>;
    case 'search':
      return <svg {...props}><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></svg>;
    case 'folder':
      return <svg {...props}><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" /></svg>;
    case 'board':
      return <svg {...props}><rect x="3" y="3" width="7" height="18" rx="1.5" /><rect x="14" y="3" width="7" height="11" rx="1.5" /></svg>;
    case 'graph':
      return <svg {...props}><circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="6" r="2.5" /><circle cx="12" cy="18" r="2.5" /><path d="M8 7.5 16 7.5M7.5 8 12 16M16.5 8 12 16" /></svg>;
    case 'cognition':
      return <svg {...props}><path d="M12 3a4 4 0 0 0-4 4v.5A3 3 0 0 0 6 13a3 3 0 0 0 2 2.8V18a3 3 0 0 0 3 3 3 3 0 0 0 3-3v-2.2A3 3 0 0 0 16 13a3 3 0 0 0-2-5.5V7a4 4 0 0 0-2-4Z" /></svg>;
    case 'stethoscope':
      return <svg {...props}><path d="M6 3v6a4 4 0 0 0 8 0V3" /><path d="M10 13v3a5 5 0 0 0 10 0v-1" /><circle cx="20" cy="11" r="2" /></svg>;
    case 'pulse':
      return <svg {...props}><path d="M3 12h4l2-5 4 10 2-5h6" /></svg>;
    case 'session':
      return <svg {...props}><rect x="3" y="4" width="18" height="14" rx="2" /><path d="m9 9 4 3-4 3" /><path d="M14 15h4" /></svg>;
    case 'settings':
      return <svg {...props}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z" /></svg>;
    default:
      return null;
  }
}
