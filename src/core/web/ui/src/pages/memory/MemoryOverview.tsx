import type { ReactNode } from 'react';
import type { MemoryStats } from './memory-derive';
import type { RoiData } from './memory-types';

// The header answers "is this working?" with counts, not a mood: how many
// lessons exist, how many have ever been confirmed, how many graduated, how
// many are decaying — then names the one mechanism that moves those numbers.

function Tile({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: number | string;
  hint: string;
  tone?: string;
}) {
  return (
    <div className="rounded-xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/50 px-4 py-3">
      <div className="text-[11px] font-medium uppercase tracking-wide text-[var(--cos-muted)]">
        {label}
      </div>
      <div
        className="mt-1 text-2xl font-semibold tabular-nums"
        style={{ color: tone ?? 'var(--cos-text)' }}
      >
        {value}
      </div>
      <div className="mt-0.5 text-[11px] leading-relaxed text-[var(--cos-faint)]">{hint}</div>
    </div>
  );
}

function votesLine(roi: RoiData | null, loading: boolean, failed: boolean): ReactNode {
  if (loading) return 'Loading validation votes…';
  if (failed || !roi) return 'Validation votes unavailable — /api/patterns/roi did not answer.';
  if (roi.validations_30d === 0)
    return 'No validation votes in the last 30 days — nothing has been confirmed or refuted.';
  const helpful = Math.round((roi.helpful_rate_30d ?? 0) * roi.validations_30d);
  return (
    <>
      <span className="tabular-nums text-[var(--cos-text)]">{roi.validations_30d}</span> validation
      vote{roi.validations_30d === 1 ? '' : 's'} in the last 30 days ·{' '}
      <span className="tabular-nums text-[var(--cos-text)]">{helpful}</span> rated helpful. It takes
      3 on the same lesson to move it out of Forming.
    </>
  );
}

export function MemoryOverview({
  stats,
  roi,
  roiLoading,
  roiFailed,
}: {
  stats: MemoryStats;
  roi: RoiData | null;
  roiLoading: boolean;
  roiFailed: boolean;
}) {
  const stalled = stats.lessons > 0 && stats.trusted === 0;

  return (
    <section aria-labelledby="memory-overview-heading" className="mb-6">
      <h2 id="memory-overview-heading" className="sr-only">
        Learning status
      </h2>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile
          label="Lessons"
          value={stats.lessons}
          hint={`plus ${stats.stats} measured stat${stats.stats === 1 ? '' : 's'}`}
        />
        <Tile
          label="Validated"
          value={stats.validated}
          hint="confirmed at least once by a session or a 👍"
          tone={stats.validated === 0 ? 'var(--cos-warn)' : 'var(--cos-ok)'}
        />
        <Tile
          label="Promoted"
          value={stats.promoted}
          hint="graduated out of memory into a durable rule"
          tone={stats.promoted > 0 ? 'var(--cos-ok)' : undefined}
        />
        <Tile
          label="Decaying"
          value={stats.fading}
          hint="tier Fading — confidence slipping, due for re-validation"
          tone={stats.fading > 0 ? 'var(--cos-warn)' : undefined}
        />
      </div>

      <div className="mt-3 rounded-xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/40 px-4 py-3 text-[13px] leading-relaxed text-[var(--cos-muted)]">
        {stalled ? (
          <p>
            <span className="font-medium text-[var(--cos-text)]">
              {stats.validated} of {stats.lessons} lessons {stats.validated === 1 ? 'has' : 'have'}{' '}
              ever been confirmed, so none has reached Trusted.
            </span>{' '}
            A lesson graduates only when its confidence is at least 70% <em>and</em> it has been
            confirmed 3 times. Confirmation has exactly one entry point:{' '}
            <code className="rounded bg-[var(--cos-overlay)] px-1 py-0.5 font-mono text-[11px] text-[var(--cos-text)]">
              cos_learn_validate(pattern_id, was_helpful)
            </code>{' '}
            — the 👍 / 👎 on each card calls it for you. Without it confidence only decays, and
            lessons accumulate without ever graduating.
          </p>
        ) : (
          <p>
            <span className="font-medium text-[var(--cos-text)]">
              {stats.trusted} of {stats.lessons} lessons have reached Trusted
            </span>{' '}
            (confidence ≥ 70% and confirmed 3 times). Confidence moves only through{' '}
            <code className="rounded bg-[var(--cos-overlay)] px-1 py-0.5 font-mono text-[11px] text-[var(--cos-text)]">
              cos_learn_validate
            </code>{' '}
            — the 👍 / 👎 on each card.
          </p>
        )}
        <p className="mt-2 text-[var(--cos-faint)]">{votesLine(roi, roiLoading, roiFailed)}</p>
        {stats.truncated && (
          <p className="mt-2 text-[var(--cos-warn)]">
            Showing {stats.fetched} of {stats.total} stored rows — the server caps this list, so the
            counts above describe only what was fetched.
          </p>
        )}
      </div>
    </section>
  );
}
