import { useState } from 'react';
import { apiPost } from '@/lib/api-client';
import type { PatternRow } from './memory-types';
import { evidenceSamples, splitLesson, tierStyle } from './memory-format';

export function LessonCard({ p }: { p: PatternRow }) {
  const [expanded, setExpanded] = useState(false);
  const [voted, setVoted] = useState<null | 'up' | 'down'>(null);
  const [busy, setBusy] = useState(false);
  const { situation, action } = splitLesson(p.pattern);
  const tier = p.promoted_to && p.promoted_to !== 'archived' ? 'Promoted' : p.tier || 'Forming';
  const ts = tierStyle(tier);

  async function vote(helpful: boolean): Promise<void> {
    if (busy || voted) return;
    setBusy(true);
    try {
      await apiPost(`/api/patterns/${p.id}/validate`, { was_helpful: helpful });
      setVoted(helpful ? 'up' : 'down');
    } catch {
      /* fail-open — feedback is best-effort */
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] px-4 py-3 transition-colors hover:border-[var(--cos-border-strong)]">
      {/* L1 — what went wrong, in plain words */}
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium leading-snug text-[var(--cos-text)]">{situation}</p>
        <span
          className="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium"
          style={{ backgroundColor: ts.bg, color: ts.fg }}
          title={
            tier === 'Promoted'
              ? `Graduated into ${p.promoted_to}`
              : tier === 'Trusted'
                ? 'Confirmed repeatedly'
                : tier === 'Fading'
                  ? 'Decaying — up for re-validation'
                  : 'Seen, not yet confirmed'
          }
        >
          {tier}
        </span>
      </div>

      {/* L2 — what to do instead */}
      {action && (
        <p className="mt-1.5 text-sm leading-snug text-[var(--cos-muted)]">
          <span className="font-semibold" style={{ color: 'var(--cos-ok)' }}>
            Do:{' '}
          </span>
          {action}
        </p>
      )}

      {/* L2 meta + feedback affordance */}
      <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-[var(--cos-muted)]">
        {p.domain && (
          <span
            className="rounded px-1.5 py-0.5 font-medium"
            style={{ backgroundColor: 'var(--cos-brand-tint)', color: 'var(--cos-brand-text)' }}
          >
            {p.domain}
          </span>
        )}
        <span className="tabular-nums">
          Seen {p.times_validated > 0 ? `${p.times_validated}×` : 'recently'}
        </span>
        {p.times_violated > 0 && (
          <span className="tabular-nums" style={{ color: 'var(--cos-err)' }}>
            came back {p.times_violated}×
          </span>
        )}
        <span className="flex items-center gap-1.5">
          {voted ? (
            <span style={{ color: 'var(--cos-ok)' }}>Thanks — recorded</span>
          ) : (
            <>
              <span>Useful?</span>
              <button
                type="button"
                onClick={() => vote(true)}
                disabled={busy}
                aria-label="Mark this lesson useful"
                className="rounded px-1 leading-none hover:bg-[var(--cos-overlay)] disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-focus)]"
              >
                👍
              </button>
              <button
                type="button"
                onClick={() => vote(false)}
                disabled={busy}
                aria-label="Mark this lesson not useful"
                className="rounded px-1 leading-none hover:bg-[var(--cos-overlay)] disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-focus)]"
              >
                👎
              </button>
            </>
          )}
        </span>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="ml-auto underline decoration-dotted underline-offset-2 hover:text-[var(--cos-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-focus)]"
        >
          {expanded ? 'Hide detail' : 'Technical detail'}
        </button>
      </div>

      {/* L3 — opt-in raw detail for power users */}
      {expanded && (
        <div className="mt-2 space-y-1 rounded-md border border-[var(--cos-border)] bg-[var(--cos-overlay)] px-3 py-2 text-xs text-[var(--cos-muted)]">
          <div>
            <span className="text-[var(--cos-text)]">Raw signature:</span> {p.pattern}
          </div>
          <div className="tabular-nums">
            Source: {p.source ?? '—'} · Confidence: {Math.round((p.confidence ?? 0) * 100)}% ·
            Provenance: {p.provenance ?? '—'}
          </div>
          {evidenceSamples(p).length > 0 && (
            <div>
              <span className="text-[var(--cos-text)]">Evidence:</span>
              <ul className="mt-0.5 list-inside list-disc space-y-0.5">
                {evidenceSamples(p).map((sample, i) => (
                  <li key={i} className="break-all">
                    {sample}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Stats ARE about percentages — a success rate is the point — so a compact
// numeric card is correct here (unlike lessons). Never carries feedback.
export function StatCard({ p }: { p: PatternRow }) {
  const pct = Math.round((p.confidence ?? 0) * 100);
  return (
    <div className="rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm leading-snug text-[var(--cos-muted)]">{p.pattern}</p>
        {p.domain && (
          <span
            className="shrink-0 rounded px-1.5 py-0.5 text-[11px] font-medium"
            style={{ backgroundColor: 'var(--cos-brand-tint)', color: 'var(--cos-brand-text)' }}
          >
            {p.domain}
          </span>
        )}
      </div>
      <div className="mt-2 flex items-center gap-2 text-xs text-[var(--cos-muted)]">
        <span
          className="h-1.5 w-28 overflow-hidden rounded-full"
          style={{ backgroundColor: 'var(--cos-overlay)' }}
        >
          <span
            className="block h-full rounded-full"
            style={{ width: `${pct}%`, backgroundColor: 'var(--cos-ok)' }}
          />
        </span>
        <span className="tabular-nums text-[var(--cos-text)]">{pct}%</span>
        <span>signal strength</span>
      </div>
    </div>
  );
}

