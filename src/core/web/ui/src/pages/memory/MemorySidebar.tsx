import { AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import { budgetRatio, type MemoryBudget, type MemoryPayload } from './memory-view';

const WARN_RATIO = 0.9;

type Tone = 'ok' | 'warn' | 'err';

const TONE_TEXT: Record<Tone, string> = {
  ok: 'text-[var(--cos-ok)]',
  warn: 'text-[var(--cos-warn)]',
  err: 'text-[var(--cos-err)]',
};

const TONE_FILL: Record<Tone, string> = {
  ok: 'bg-[var(--cos-ok)]',
  warn: 'bg-[var(--cos-warn)]',
  err: 'bg-[var(--cos-err)]',
};

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/60 p-4">
      <h2 className="mb-3 text-[10px] font-mono uppercase tracking-[0.16em] text-[var(--cos-muted)]">
        {title}
      </h2>
      {children}
    </section>
  );
}

export function HealthCard({ lint }: { lint: NonNullable<MemoryPayload['lint']> }) {
  const { errors, warnings, summary } = lint;
  const state: Tone = errors.length ? 'err' : warnings.length ? 'warn' : 'ok';
  const Icon = state === 'err' ? XCircle : state === 'warn' ? AlertTriangle : CheckCircle2;
  const headline =
    state === 'err'
      ? `${errors.length} ${errors.length === 1 ? 'error' : 'errors'}`
      : state === 'warn'
        ? `${warnings.length} ${warnings.length === 1 ? 'warning' : 'warnings'}`
        : 'Healthy';
  return (
    <Card title="Lint">
      <div className="flex items-start gap-3">
        <Icon size={28} aria-hidden className={`shrink-0 ${TONE_TEXT[state]}`} />
        <div className="min-w-0">
          <div className="text-base font-semibold text-[var(--cos-text)]">{headline}</div>
          <p className="mt-0.5 text-xs leading-relaxed text-[var(--cos-muted)]">{summary}</p>
        </div>
      </div>
      {(errors.length > 0 || warnings.length > 0) && (
        <ul className="mt-3 space-y-1.5">
          {errors.map((finding) => (
            <li
              key={`e-${finding}`}
              className="rounded-lg bg-[var(--cos-err-tint)] px-2.5 py-1.5 font-mono text-[11px] leading-snug text-[var(--cos-err)]"
            >
              {finding}
            </li>
          ))}
          {warnings.map((finding) => (
            <li
              key={`w-${finding}`}
              className="rounded-lg bg-[var(--cos-warn-tint)] px-2.5 py-1.5 font-mono text-[11px] leading-snug text-[var(--cos-warn)]"
            >
              {finding}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-[11px] text-[var(--cos-muted)]">
        Same check as <code className="font-mono">make memory-lint</code>.
      </p>
    </Card>
  );
}

function Meter({
  label,
  used,
  max,
  unit,
}: {
  label: string;
  used: number;
  max: number;
  unit: string;
}) {
  const ratio = budgetRatio(used, max);
  const tone: Tone = ratio >= 1 ? 'err' : ratio >= WARN_RATIO ? 'warn' : 'ok';
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-xs">
        <span className="text-[var(--cos-text)]">{label}</span>
        <span className="font-mono text-[var(--cos-muted)]">
          {used.toLocaleString()} / {max.toLocaleString()} {unit}
        </span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={used}
        className="h-1.5 overflow-hidden rounded-full bg-[var(--cos-border)]"
      >
        <div
          className={`h-full rounded-full ${TONE_FILL[tone]}`}
          style={{ width: `${Math.max(ratio * 100, 2)}%` }}
        />
      </div>
    </div>
  );
}

export function BudgetCard({ budget }: { budget: MemoryBudget }) {
  return (
    <Card title="MEMORY.md load budget">
      <div className="space-y-3">
        <Meter label="Lines" used={budget.lines} max={budget.max_lines} unit="lines" />
        <Meter label="Size" used={budget.bytes} max={budget.max_bytes} unit="bytes" />
      </div>
      <p className="mt-3 text-[11px] leading-relaxed text-[var(--cos-muted)]">
        Claude Code loads only this much of the index. A line past the limit is a memory no session
        sees.
      </p>
    </Card>
  );
}

export function TypeFilter({
  counts,
  total,
  selected,
  onSelect,
}: {
  counts: Array<[string, number]>;
  total: number;
  selected: string | null;
  onSelect: (type: string | null) => void;
}) {
  const options: Array<[string | null, string, number]> = [
    [null, 'All', total],
    ...counts.map(([type, count]): [string, string, number] => [type, type, count]),
  ];
  return (
    <Card title="Type">
      <div className="flex flex-col gap-0.5">
        {options.map(([value, label, count]) => {
          const active = selected === value;
          return (
            <button
              key={label}
              type="button"
              aria-pressed={active}
              onClick={() => onSelect(value)}
              className={[
                'flex items-center justify-between rounded-lg px-2.5 py-1.5 text-xs capitalize transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]',
                active
                  ? 'bg-[var(--cos-accent-solid)] text-white'
                  : 'text-[var(--cos-text)] hover:bg-white/5',
              ].join(' ')}
            >
              <span className="flex items-center gap-2">
                <TypeDot type={value} />
                {label}
              </span>
              <span className={`font-mono ${active ? 'text-white/80' : 'text-[var(--cos-muted)]'}`}>
                {count}
              </span>
            </button>
          );
        })}
      </div>
    </Card>
  );
}

const TYPE_TONE: Record<string, string> = {
  feedback: 'bg-[var(--accent)]',
  project: 'bg-[var(--cos-ok)]',
  reference: 'bg-[var(--cos-muted)]',
  user: 'bg-[var(--cos-warn)]',
};

export function TypeDot({ type }: { type: string | null }) {
  if (!type)
    return (
      <span aria-hidden className="h-1.5 w-1.5 rounded-full border border-[var(--cos-muted)]" />
    );
  return (
    <span
      aria-hidden
      className={`h-1.5 w-1.5 rounded-full ${TYPE_TONE[type] ?? 'bg-[var(--cos-border)]'}`}
    />
  );
}
