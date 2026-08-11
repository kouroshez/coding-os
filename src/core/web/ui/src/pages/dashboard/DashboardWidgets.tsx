import { Link } from 'react-router-dom';
import { Activity, Brain, KanbanSquare, MessageSquare, Zap } from 'lucide-react';
import type { HookEvent } from './dashboard-types';
import { ACTION_BADGE, NEUTRAL_BADGE, relIso } from './dashboard-format';

// ─────────────────────────────────────────────────────────────────────────
// Building blocks
// ─────────────────────────────────────────────────────────────────────────

export function DashboardHeader({
  presentCount,
  lastHook,
}: {
  presentCount: number;
  lastHook: HookEvent | null;
}) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-2">
      <div>
        <h1 className="text-xl font-semibold text-[var(--cos-text)]">Overview</h1>
        <p className="mt-0.5 text-xs text-[var(--cos-muted)]">
          {presentCount > 0 ? (
            <>
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--cos-ok-tint)] align-middle" />{' '}
              {presentCount} agent{presentCount === 1 ? '' : 's'} live · last hook{' '}
              <span className="font-mono text-[var(--cos-text)]">
                {lastHook?.hook ?? '—'}
              </span>{' '}
              <span className="text-[var(--cos-faint)]">{relIso(lastHook?.iso_ts)} ago</span>
            </>
          ) : (
            'idle · open Claude / Codex to see live activity.'
          )}
        </p>
      </div>
    </header>
  );
}

export function QuickActions({
  currentChat,
  activeSessionAgent,
  activeSession,
  scopedLink,
}: {
  currentChat: string | null;
  activeSessionAgent: string | null;
  activeSession: string | null;
  scopedLink: (featurePath: string, suffix?: string) => string;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      {currentChat && (
        <Link
          to={scopedLink('cognition', `${encodeURIComponent(currentChat)}?view=chat`)}
          className="inline-flex items-center gap-1.5 rounded-md border border-[var(--cos-accent)] bg-[var(--cos-accent)]/10 px-3 py-1.5 text-[11px] font-semibold text-[var(--cos-accent)] hover:bg-[var(--cos-accent)]/20"
        >
          <MessageSquare size={12} aria-hidden /> Open current chat
        </Link>
      )}
      {activeSession && (
        <Link
          to={scopedLink('cognition', encodeURIComponent(activeSession))}
          className="inline-flex items-center gap-1.5 rounded-md border border-[var(--cos-border)] px-3 py-1.5 text-[11px] text-[var(--cos-text)] hover:border-[var(--cos-accent)]"
        >
          <Brain size={12} aria-hidden /> {activeSessionAgent ?? 'agent'} trace
        </Link>
      )}
      <Link
        to={scopedLink('cognition', '?view=live')}
        className="inline-flex items-center gap-1.5 rounded-md border border-[var(--cos-border)] px-3 py-1.5 text-[11px] text-[var(--cos-text)] hover:border-[var(--cos-accent)]"
      >
        <Zap size={12} aria-hidden /> Live hook stream
      </Link>
      <Link
        to={scopedLink('board')}
        className="inline-flex items-center gap-1.5 rounded-md border border-[var(--cos-border)] px-3 py-1.5 text-[11px] text-[var(--cos-text)] hover:border-[var(--cos-accent)]"
      >
        <KanbanSquare size={12} aria-hidden /> Board
      </Link>
      <Link
        to={scopedLink('search')}
        className="inline-flex items-center gap-1.5 rounded-md border border-[var(--cos-border)] px-3 py-1.5 text-[11px] text-[var(--cos-text)] hover:border-[var(--cos-accent)]"
      >
        <Activity size={12} aria-hidden /> Search
      </Link>
    </div>
  );
}

export function KpiCard({
  Icon,
  label,
  value,
  hint,
  tone,
  bar,
}: {
  Icon: typeof Activity;
  label: string;
  value: string;
  hint?: string;
  tone: 'neutral' | 'positive' | 'warning' | 'danger';
  bar?: { pct: number; warn: boolean };
}) {
  const toneClass = {
    neutral: 'text-[var(--cos-text)]',
    positive: 'text-[var(--cos-ok)] glow-emerald',
    warning: 'text-[var(--cos-warn)] glow-amber',
    danger: 'text-[var(--cos-err)] glow-rose',
  }[tone];

  const borderClass = {
    neutral: 'border-white/5 shadow-white/5',
    positive: 'border-[var(--cos-ok)]  hover:border-[var(--cos-ok)]',
    warning: 'border-[var(--cos-warn)]  hover:border-[var(--cos-warn)]',
    danger: 'border-[var(--cos-err)]  hover:border-[var(--cos-err)]',
  }[tone];

  return (
    <section className={['glass-card rounded-xl border p-4 transition-all duration-300 relative overflow-hidden flex flex-col justify-between hover:-translate-y-0.5 hover:shadow-xl group', borderClass].join(' ')}>
      <div>
        <div className="mb-2.5 flex items-center gap-1.5 text-[10px] uppercase tracking-widest font-semibold text-[var(--cos-muted)] group-hover:text-[var(--cos-text)] transition-colors">
          <Icon size={12} aria-hidden />
          {label}
        </div>
        <div className={['font-mono text-3xl font-extrabold leading-none', toneClass].join(' ')}>{value}</div>
      </div>
      <div className="mt-3">
        {hint && <div className="text-[10px] font-medium text-[var(--cos-faint)]">{hint}</div>}
        {bar && (
          <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-white/5">
            <div
              className={bar.warn ? 'h-full bg-[var(--cos-warn-tint)] shadow-[0_0_8px_rgba(245,158,11,0.5)]' : 'h-full bg-[var(--cos-accent)] shadow-[0_0_8px_var(--cos-accent)]'}
              style={{ width: `${Math.min(100, bar.pct)}%` }}
            />
          </div>
        )}
      </div>
    </section>
  );
}

export function PanelCard({
  Icon,
  title,
  link,
  linkLabel,
  children,
}: {
  Icon: typeof Activity;
  title: string;
  link: string | null;
  linkLabel?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="glass-card flex min-h-[280px] flex-col rounded-xl border border-white/5 p-4 transition-all duration-300 hover:shadow-2xl">
      <header className="mb-3.5 flex items-center gap-2 border-b border-white/5 pb-2.5">
        <Icon size={14} aria-hidden className="text-[var(--cos-muted)]" />
        <h2 className="text-xs font-bold uppercase tracking-wider text-[var(--cos-text)]">
          {title}
        </h2>
        {link && (
          <Link to={link} className="ml-auto text-[10px] font-bold uppercase tracking-wider text-[var(--cos-accent)] hover:opacity-85">
            {linkLabel ?? 'open →'}
          </Link>
        )}
      </header>
      <div className="flex-1 min-h-0">{children}</div>
    </section>
  );
}

export function ActionBadge({ action }: { action: string }) {
  const norm = action.toLowerCase();
  const pal = ACTION_BADGE[norm] ?? NEUTRAL_BADGE;
  return (
    <span
      className={['inline-block min-w-[3.25rem] shrink-0 whitespace-nowrap rounded px-1.5 py-0.5 text-center font-mono text-[9px] font-semibold uppercase tracking-wider', pal.bg, pal.text].join(' ')}
      title={action}
    >
      {'label' in pal && pal.label ? pal.label : norm}
    </span>
  );
}

export function AgentBadge({ agent, active }: { agent: string; active: boolean }) {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-[var(--cos-border)] px-1 py-0.5 text-[9px] uppercase tracking-wider text-[var(--cos-muted)]">
      {active && (
        <span aria-hidden className="inline-block h-1 w-1 animate-pulse rounded-full bg-[var(--cos-ok-tint)]" />
      )}
      {agent}
    </span>
  );
}

export function Badge({
  children,
  tone = 'muted',
}: {
  children: React.ReactNode;
  tone?: 'muted' | 'accent' | 'danger';
}) {
  const cls =
    tone === 'accent'
      ? 'bg-[var(--cos-accent)]/15 text-[var(--cos-accent)]'
      : tone === 'danger'
      ? 'bg-[var(--cos-err-tint)] text-[var(--cos-err)]'
      : 'bg-[var(--cos-border)]/30 text-[var(--cos-muted)]';
  return (
    <span className={['rounded px-1 py-0.5 text-[9px] uppercase tracking-wider', cls].join(' ')}>{children}</span>
  );
}

export function StatTile({
  label,
  value,
  subtitle,
  tone,
}: {
  label: string;
  value: number;
  subtitle?: string;
  tone?: 'neutral' | 'warning' | 'danger';
}) {
  const valueClass =
    tone === 'danger' && value > 0
      ? 'text-[var(--cos-err)]'
      : tone === 'warning'
      ? 'text-[var(--cos-warn)]'
      : 'text-[var(--cos-text)]';
  return (
    <div className="rounded-md border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1.5">
      <div className={['font-mono text-xl font-semibold leading-none', valueClass].join(' ')}>
        {value}
      </div>
      <div className="mt-1 text-[9px] uppercase tracking-wider text-[var(--cos-muted)]">{label}</div>
      {subtitle && <div className="text-[9px] text-[var(--cos-faint)]">{subtitle}</div>}
    </div>
  );
}

export function Sparkbars({ data }: { data: { day: string; total: number }[] }) {
  const max = Math.max(0.0001, ...data.map((d) => d.total));
  const today = new Date().toISOString().slice(0, 10);
  return (
    <div className="flex h-12 items-end gap-1">
      {data.map((d) => {
        const h = max > 0 ? Math.max(2, (d.total / max) * 44) : 2;
        const isToday = d.day === today;
        return (
          <div
            key={d.day}
            className="group relative flex flex-1 flex-col items-center"
            title={`${d.day} · $${d.total.toFixed(4)}`}
          >
            <div
              className={[
                'w-full rounded-t transition-colors',
                isToday ? 'bg-[var(--cos-accent)]' : 'bg-[var(--cos-border)]',
              ].join(' ')}
              style={{ height: `${h}px` }}
            />
            <span className="mt-1 font-mono text-[8px] text-[var(--cos-faint)]">
              {d.day.slice(-2)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function EmptyState({
  icon,
  text,
  subtext,
}: {
  icon: string;
  text: string;
  subtext?: string;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-1 px-4 py-6 text-center">
      <span aria-hidden className="text-2xl text-[var(--cos-faint)]">
        {icon}
      </span>
      <p className="text-xs text-[var(--cos-muted)]">{text}</p>
      {subtext && <p className="text-[10px] text-[var(--cos-faint)]">{subtext}</p>}
    </div>
  );
}

export function Skeleton({ rows }: { rows: number }) {
  return (
    <ul className="space-y-1.5">
      {Array.from({ length: rows }).map((_, i) => (
        <li key={i} className="h-6 animate-pulse rounded bg-[var(--cos-border)]/20" />
      ))}
    </ul>
  );
}
