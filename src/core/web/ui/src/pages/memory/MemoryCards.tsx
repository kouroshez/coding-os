import { useState } from 'react';
import type { ReactNode } from 'react';
import { apiPost } from '@/lib/api-client';
import type { PatternRow } from './memory-types';
import {
  ageLabel,
  confidenceBand,
  dateLabel,
  evidenceSamples,
  isPromoted,
  pct,
  sourceCopy,
  splitLesson,
  tierStyle,
  typeLabel,
} from './memory-format';

function Badge({ children, bg, fg }: { children: ReactNode; bg: string; fg: string }) {
  return (
    <span
      className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium"
      style={{ backgroundColor: bg, color: fg }}
    >
      {children}
    </span>
  );
}

function MetaItem({ children }: { children: ReactNode }) {
  return <span className="whitespace-nowrap">{children}</span>;
}

function TechnicalDetail({ p }: { p: PatternRow }) {
  const samples = evidenceSamples(p);
  return (
    <div className="mt-2 space-y-1 rounded-lg border border-[var(--cos-border)] bg-[var(--cos-overlay)] px-3 py-2 text-[11px] leading-relaxed text-[var(--cos-muted)]">
      <div>
        <span className="text-[var(--cos-text)]">Raw signature:</span> {p.pattern}
      </div>
      <div className="tabular-nums">
        provenance {p.provenance || '—'} · impact {p.impact_score?.toFixed?.(2) ?? '—'} · decay{' '}
        {p.decay_rate?.toFixed?.(3) ?? '—'} · reads {p.access_count} · trust tier {p.trust_tier} ·
        computed tier {p.tier}
      </div>
      <div>
        Last validated {dateLabel(p.last_validated)} · last read {dateLabel(p.last_accessed_at)}
      </div>
      {p.promoted_to && (
        <div>
          <span className="text-[var(--cos-text)]">Promoted to:</span> {p.promoted_to}
        </div>
      )}
      {samples.length > 0 && (
        <div>
          <span className="text-[var(--cos-text)]">Evidence:</span>
          <ul className="mt-0.5 list-inside list-disc space-y-0.5">
            {samples.map((sample, i) => (
              <li key={i} className="break-all">
                {sample}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function LessonCard({ p }: { p: PatternRow }) {
  const [expanded, setExpanded] = useState(false);
  const [voted, setVoted] = useState<null | 'up' | 'down'>(null);
  const [busy, setBusy] = useState(false);
  const [voteError, setVoteError] = useState('');
  const { situation, action } = splitLesson(p.pattern);
  const band = confidenceBand(p.confidence ?? 0);
  const tier = tierStyle(p.tier);

  // 👍 / 👎 posts to /api/patterns/<id>/validate, which calls cos_learn_validate
  // — the only path that moves a pattern's confidence (LTP / LTD).
  async function vote(helpful: boolean): Promise<void> {
    if (busy || voted) return;
    setBusy(true);
    setVoteError('');
    try {
      await apiPost(`/api/patterns/${p.id}/validate`, { was_helpful: helpful });
      setVoted(helpful ? 'up' : 'down');
    } catch (err) {
      setVoteError(err instanceof Error ? err.message : 'vote failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="px-4 py-3 transition-colors hover:bg-white/[0.02]">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[13px] font-medium leading-snug text-[var(--cos-text)]">{situation}</p>
        <div className="flex shrink-0 flex-wrap items-center gap-1.5">
          {isPromoted(p) && (
            <Badge bg="var(--cos-brand-tint)" fg="var(--cos-brand-text)">
              promoted
            </Badge>
          )}
          {tier && (
            <Badge bg={tier.bg} fg={tier.fg}>
              {p.tier}
            </Badge>
          )}
        </div>
      </div>

      {action && (
        <p className="mt-1.5 text-[13px] leading-snug text-[var(--cos-muted)]">
          <span className="font-semibold text-[var(--cos-ok)]">Do: </span>
          {action}
        </p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--cos-faint)]">
        <MetaItem>
          <span className="text-[var(--cos-muted)]">{typeLabel(p.memory_type)}</span>
        </MetaItem>
        <MetaItem>{sourceCopy(p.source).label}</MetaItem>
        {p.domain && <MetaItem>{p.domain}</MetaItem>}
        <MetaItem>
          Confidence{' '}
          <span className="tabular-nums text-[var(--cos-text)]">{pct(p.confidence)}</span>{' '}
          <span style={{ color: band.token }}>{band.label}</span>
        </MetaItem>
        <MetaItem>
          {p.times_validated > 0 ? (
            <>
              Validated{' '}
              <span className="tabular-nums text-[var(--cos-ok)]">{p.times_validated}×</span>
            </>
          ) : (
            <span className="text-[var(--cos-warn)]">Never validated</span>
          )}
        </MetaItem>
        {/* times_violated has exactly one writer: the 👎 branch of
            _learning_validate.py — it counts refutations, not recurrences. */}
        {p.times_violated > 0 && (
          <MetaItem>
            <span className="text-[var(--cos-err)] tabular-nums">
              Marked unhelpful {p.times_violated}×
            </span>
          </MetaItem>
        )}
        <MetaItem>Added {ageLabel(p.created_at)}</MetaItem>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--cos-muted)]">
        {voted ? (
          <span className="text-[var(--cos-ok)]">Thanks — recorded as a validation</span>
        ) : (
          <span className="flex items-center gap-1.5">
            <span>Did this lesson help?</span>
            <button
              type="button"
              onClick={() => vote(true)}
              disabled={busy}
              aria-label="Mark this lesson helpful — records a validation"
              className="rounded px-1 leading-none hover:bg-[var(--cos-overlay)] disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-focus)]"
            >
              👍
            </button>
            <button
              type="button"
              onClick={() => vote(false)}
              disabled={busy}
              aria-label="Mark this lesson unhelpful — records a refutation"
              className="rounded px-1 leading-none hover:bg-[var(--cos-overlay)] disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-focus)]"
            >
              👎
            </button>
          </span>
        )}
        {voteError && <span className="text-[var(--cos-err)]">{voteError}</span>}
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="ml-auto underline decoration-dotted underline-offset-2 hover:text-[var(--cos-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-focus)]"
        >
          {expanded ? 'Hide detail' : 'Technical detail'}
        </button>
      </div>

      {expanded && <TechnicalDetail p={p} />}
    </article>
  );
}

// A stat row is a measured baseline, not a belief. Its success rate is inside
// the text; `confidence` here is sample-size confidence (_learning_extract.py
// computes min(0.85, 0.4 + n/20)), so it is labelled as exactly that.
export function StatCard({ p }: { p: PatternRow }) {
  const band = confidenceBand(p.confidence ?? 0);
  return (
    <article className="px-4 py-3 transition-colors hover:bg-white/[0.02]">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[13px] leading-snug text-[var(--cos-text)]">{p.pattern}</p>
        <Badge bg="var(--cos-inset)" fg="var(--cos-muted)">
          measured
        </Badge>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--cos-faint)]">
        {p.domain && <MetaItem>{p.domain}</MetaItem>}
        <MetaItem>
          Sample confidence{' '}
          <span className="tabular-nums text-[var(--cos-text)]">{pct(p.confidence)}</span>{' '}
          <span style={{ color: band.token }}>{band.label}</span>
        </MetaItem>
        <MetaItem>Measured {ageLabel(p.created_at)}</MetaItem>
      </div>
    </article>
  );
}
