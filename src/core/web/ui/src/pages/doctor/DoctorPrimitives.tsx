import type * as React from 'react';

export function Section({
  title,
  cols,
  children,
}: {
  title: React.ReactNode;
  cols?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={['glass-card rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/50 p-5 text-xs transition-all duration-200 hover:-translate-y-0.5 shadow-sm', cols ?? ''].join(' ')}>
      <h3 className="mb-3 text-[11px] font-bold uppercase tracking-wider text-[var(--accent)]">{title}</h3>
      {children}
    </section>
  );
}

export function Row({ k, v, danger }: { k: string; v: string; danger?: boolean }) {
  return (
    <div className="flex justify-between items-center py-2 border-b border-[var(--cos-border)] last:border-b-0 text-[11px]">
      <span className="text-[var(--cos-muted)] font-medium">{k}</span>
      <span className={danger ? 'font-mono text-[var(--cos-err)] glow-rose font-semibold' : 'font-mono text-[var(--cos-text)] font-semibold'}>{v}</span>
    </div>
  );
}
