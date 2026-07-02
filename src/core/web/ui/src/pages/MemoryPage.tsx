import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

// Field names mirror src/core/web/routes/patterns.py::_COLUMNS + the computed
// `tier` field (api-contract-discipline — the producer is the source of truth).
interface PatternRow {
  id: number;
  pattern: string;
  memory_type: string;
  domain: string | null;
  source: string | null;
  confidence: number;
  decay_rate: number;
  impact_score: number;
  times_validated: number;
  times_violated: number;
  access_count: number;
  trust_tier: string;
  tier: string; // Forming | Trusted | Fading — computed by pattern_tier()
  provenance: string;
  promoted_to: string | null;
  evidence_json: string | null;
  last_validated: string | null;
  last_accessed_at: string | null;
  created_at: string;
}

interface PatternsEnvelope {
  ok: boolean;
  data: { patterns: PatternRow[]; count: number; total_count: number };
}

// Field names mirror src/core/web/routes/patterns.py::learning_roi exactly.
interface RoiSession {
  session_id: string;
  friction: number;
  total: number;
  rate: number;
  started: string;
}
interface RoiData {
  sessions: RoiSession[];
  count: number;
  trend: string;
  delta_pct: number;
  validations_30d: number;
  helpful_rate_30d: number | null;
}
interface RoiEnvelope {
  ok: boolean;
  data: RoiData;
}

function roiColor(trend: string): string {
  if (trend === 'improving') return 'var(--cos-ok)';
  if (trend === 'worsening') return 'var(--cos-err)';
  return 'var(--cos-muted)';
}
// Plain-language read-out — the section must answer "is it working?" in words a
// novice gets, and stay honest when there isn't enough history to judge a trend.
// Direct outcome evidence (did surfaced lessons help?) outranks the stumble
// trend once enough votes exist — MIN_VALIDATIONS guards against judging on noise.
const MIN_VALIDATIONS = 5;

function hasHelpfulSignal(roi: RoiData | null): roi is RoiData {
  return !!roi && roi.validations_30d >= MIN_VALIDATIONS && roi.helpful_rate_30d !== null;
}
function roiHeadline(roi: RoiData | null, trend: string, enough: boolean): string {
  if (hasHelpfulSignal(roi)) {
    const pct = Math.round((roi.helpful_rate_30d as number) * 100);
    if (pct >= 60) return `Yes — lessons are holding up (${pct}% rated helpful)`;
    if (pct < 40) return `Lessons aren’t landing (${pct}% rated helpful)`;
    return `Mixed — ${pct}% of surfaced lessons rated helpful`;
  }
  if (!enough) return 'Too early to tell';
  if (trend === 'improving') return 'Yes — fewer stumbles lately';
  if (trend === 'worsening') return 'Stumbles ticked up recently';
  return 'Steady — stumbles aren’t rising';
}
function roiSentence(roi: RoiData | null, trend: string, enough: boolean): string {
  if (hasHelpfulSignal(roi))
    return `Based on ${roi.validations_30d} validations in the last 30 days — a lesson counts as helpful when its failure did not recur after being surfaced.`;
  if (!enough)
    return 'coding-os needs a few more work sessions before it can tell whether the agent’s stumbles (blocked actions + errors) are trending down.';
  if (trend === 'improving')
    return 'The agent is hitting fewer blocked actions and errors than before — the lessons are paying off.';
  if (trend === 'worsening')
    return 'The agent hit more blocked actions and errors recently — worth a look at what changed.';
  return 'The agent’s blocked actions and errors are holding steady across recent sessions.';
}

function api(slug: string | undefined, path: string): string {
  const base = slug ? `/api/p/${slug}` : '/api';
  return `${base}${path}`;
}

// Confidence tier → colour. Meaning, not decoration. (See learning-extraction.md.)
function tierStyle(tier: string): { bg: string; fg: string } {
  if (tier === 'Promoted') return { bg: 'var(--cos-brand-tint)', fg: 'var(--cos-brand-text)' };
  if (tier === 'Trusted') return { bg: 'var(--cos-ok-tint)', fg: 'var(--cos-ok)' };
  if (tier === 'Fading') return { bg: 'var(--cos-warn-tint)', fg: 'var(--cos-warn)' };
  return { bg: 'var(--cos-overlay)', fg: 'var(--cos-muted)' }; // Forming
}

// 'stat' rows are success-rate baselines (observability) — shown separately,
// never as a learning. Everything else is a belief/lesson.
function isStat(p: PatternRow): boolean {
  return p.memory_type === 'stat';
}

// Split ANY producer lesson format on the " → " separator: left = situation
// (what happened), right = action (what to do). Covers all 4 shapes —
// "Recurring <kind> (N occurrences): …", "Fixed repeatedly (N occurrences): …",
// "Reverted before: …", and arrow-less ([Breakthrough] …) → whole text, no action.
// Exported for unit testing (the previous regex only matched "Recurring …",
// silently dropping the action line from revert/fix lessons — audit regression).
export function splitLesson(pattern: string): { situation: string; action: string | null } {
  const arrow = pattern.lastIndexOf(' → ');
  if (arrow === -1) return { situation: pattern, action: null };
  const action = pattern.slice(arrow + 3).trim();
  const situation = pattern
    .slice(0, arrow)
    .trim()
    .replace(/^(Recurring [a-z ]+|Fixed repeatedly)\s*\(\d+ occurrences?\):\s*/i, '');
  return { situation: situation || pattern.slice(0, arrow).trim(), action };
}

// Distilled lessons store the sanitized failure samples that justified them.
function evidenceSamples(p: PatternRow): string[] {
  if (!p.evidence_json) return [];
  try {
    const parsed = JSON.parse(p.evidence_json) as { samples?: unknown };
    if (Array.isArray(parsed.samples)) return parsed.samples.map(String).slice(0, 3);
  } catch {
    /* malformed evidence is not worth an error surface */
  }
  return [];
}

// L1+L2+L3 progressive-disclosure card with 👍/👎 feedback (closes the loop).
function LessonCard({ p, slug }: { p: PatternRow; slug: string | undefined }) {
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
      await fetch(api(slug, `/patterns/${p.id}/validate`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ was_helpful: helpful }),
      });
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
function StatCard({ p }: { p: PatternRow }) {
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

type View = 'all' | 'lessons' | 'stats';

export default function MemoryPage() {
  const { slug } = useParams<{ slug?: string }>();
  const [patterns, setPatterns] = useState<PatternRow[]>([]);
  const [view, setView] = useState<View>('all');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>('');
  const [reloadCounter, setReloadCounter] = useState<number>(0);
  const [lastRun, setLastRun] = useState<string | null>(null);
  const [running, setRunning] = useState<boolean>(false);
  const [runMsg, setRunMsg] = useState<string>('');
  const [roi, setRoi] = useState<RoiData | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(api(slug, '/patterns'))
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<PatternsEnvelope>;
      })
      .then((env) => {
        if (cancelled) return;
        setPatterns(env.data?.patterns ?? []);
        setError('');
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [slug, reloadCounter]);

  // When the loop last ran (read-only) — drives the "Last run" label.
  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    fetch(`/api/scheduled/project/${encodeURIComponent(slug)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!cancelled && d) setLastRun((d.run_at as string) ?? null);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [slug, reloadCounter]);

  // Learning effectiveness: friction-per-session trend (does it go down over time?).
  useEffect(() => {
    let cancelled = false;
    fetch(api(slug, '/patterns/roi'))
      .then((r) => (r.ok ? (r.json() as Promise<RoiEnvelope>) : null))
      .then((env) => {
        if (!cancelled && env?.data) setRoi(env.data);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [slug, reloadCounter]);

  // Manual trigger — runs the same nightly loop (decay + learn-extract + digest)
  // and refetches so the freshly-distilled lessons appear immediately.
  async function runLoop(): Promise<void> {
    if (!slug || running) return;
    setRunning(true);
    setRunMsg('');
    try {
      const r = await fetch(`/api/scheduled/run/${encodeURIComponent(slug)}`, { method: 'POST' });
      const d = await r.json();
      const lx = d?.summary?.tasks?.learn_extract;
      if (d?.ran && lx?.status === 'ok') {
        const n = Array.isArray(lx.extracted) ? lx.extracted.length : 0;
        setRunMsg(
          `Done — distilled ${n} pattern${n === 1 ? '' : 's'} from ${lx.total_outcomes_analyzed ?? 0} outcomes.`,
        );
      } else if (d?.ran && lx?.status === 'skipped') {
        setRunMsg('Done — no new outcomes to learn from yet.');
      } else if (d?.ran) {
        setRunMsg('Done.');
      } else {
        setRunMsg(`Failed: ${d?.error ?? 'unknown error'}`);
      }
      setReloadCounter((c) => c + 1);
    } catch (e) {
      setRunMsg(`Failed: ${String(e)}`);
    } finally {
      setRunning(false);
    }
  }

  const isPromoted = (p: PatternRow): boolean =>
    !!p.promoted_to && p.promoted_to !== 'archived';
  const isArchived = (p: PatternRow): boolean => p.promoted_to === 'archived';
  const lessons = patterns.filter((p) => !isStat(p) && !isArchived(p));
  const promoted = lessons.filter(isPromoted);
  const activeLessons = lessons.filter((p) => !isPromoted(p));
  const lessonGroups: { label: string; hint: string; items: PatternRow[] }[] = [
    {
      label: 'Trusted',
      hint: 'confirmed repeatedly — candidates for permanent rules',
      items: activeLessons.filter((p) => (p.tier || 'Forming') === 'Trusted'),
    },
    {
      label: 'Forming',
      hint: 'seen, not yet confirmed',
      items: activeLessons.filter((p) => (p.tier || 'Forming') === 'Forming'),
    },
    {
      label: 'Fading',
      hint: 'decaying — up for re-validation',
      items: activeLessons.filter((p) => (p.tier || 'Forming') === 'Fading'),
    },
  ];
  const stats = patterns.filter(isStat);
  const showLessons = view !== 'stats';
  const showStats = view !== 'lessons';
  // A 2-3 session trend is noise; only judge "is it working?" with enough history.
  const enoughRoi = !!roi && roi.sessions.length >= 4;

  const views: { id: View; label: string }[] = [
    { id: 'all', label: 'All' },
    { id: 'lessons', label: `Lessons (${lessons.length})` },
    { id: 'stats', label: `Stats (${stats.length})` },
  ];

  return (
    <div className="h-full overflow-auto p-6">
      <div className="mx-auto max-w-3xl space-y-6">
        <header className="space-y-3">
          <h1 className="text-xl font-semibold text-[var(--cos-text)]">Agent Memory</h1>
          <p className="text-sm text-[var(--cos-muted)]">
            As the agent works it hits friction — blocked actions, failures, reworks — and turns
            the repeats into <strong className="text-[var(--cos-text)]">lessons</strong> so it
            avoids the same mistake next time. Each lesson shows{' '}
            <strong className="text-[var(--cos-text)]">what went wrong</strong>, what to{' '}
            <strong className="text-[var(--cos-text)]">do</strong> instead, and how trusted it is.
            <strong className="text-[var(--cos-text)]"> Project stats</strong> are success rates,
            shown for context — not lessons.
          </p>

          {/* View filter — plain language, not internal trust_tier jargon */}
          <div className="flex flex-wrap items-center gap-1.5">
            {views.map((v) => (
              <button
                key={v.id}
                type="button"
                onClick={() => setView(v.id)}
                className="rounded-md px-2.5 py-1 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-focus)]"
                style={
                  view === v.id
                    ? { backgroundColor: 'var(--cos-brand-tint)', color: 'var(--cos-brand-text)' }
                    : { color: 'var(--cos-muted)' }
                }
                aria-pressed={view === v.id}
              >
                {v.label}
              </button>
            ))}
          </div>

          {slug && (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] px-3 py-2 text-xs text-[var(--cos-muted)]">
              <button
                type="button"
                onClick={runLoop}
                disabled={running}
                className="rounded-md px-2.5 py-1 font-medium disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-focus)]"
                style={{ backgroundColor: 'var(--cos-brand-tint)', color: 'var(--cos-brand-text)' }}
              >
                {running ? 'Running…' : 'Run learning loop now'}
              </button>
              <span>
                Last run:{' '}
                <span className="text-[var(--cos-text)]">
                  {lastRun ? new Date(lastRun).toLocaleString() : 'never'}
                </span>
              </span>
              {runMsg && <span className="text-[var(--cos-text)]">{runMsg}</span>}
            </div>
          )}
        </header>

        {loading && <div className="text-sm text-[var(--cos-muted)]">Loading…</div>}
        {error && (
          <div className="rounded-md border border-[var(--cos-err)] bg-[var(--cos-err-tint)] px-3 py-2 text-sm text-[var(--cos-err)]">
            Failed to load patterns: {error}
          </div>
        )}
        {!loading && !error && lessons.length === 0 && (
          <div className="rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] px-4 py-6 text-sm text-[var(--cos-muted)]">
            No lessons yet — the agent hasn’t hit enough repeated friction to learn one. That’s
            healthy: it means few mistakes are recurring. Lessons appear here when the learning
            loop runs (nightly, or every 10th task), or when you press{' '}
            <strong className="text-[var(--cos-text)]">Run learning loop now</strong> above.
          </div>
        )}

        {roi && (
          <section className="rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-[var(--cos-text)]">Is it working?</h2>
              <span
                className="text-xs font-medium"
                style={{ color: enoughRoi ? roiColor(roi.trend) : 'var(--cos-muted)' }}
              >
                {enoughRoi
                  ? `${roi.trend === 'improving' ? '↓' : roi.trend === 'worsening' ? '↑' : '→'} ${roi.trend}`
                  : 'gathering data'}
              </span>
            </div>
            <p className="mt-1 text-sm font-medium text-[var(--cos-text)]">
              {roiHeadline(roi, roi.trend, enoughRoi)}
            </p>
            <p className="mt-0.5 text-xs text-[var(--cos-muted)]">
              {roiSentence(roi, roi.trend, enoughRoi)}
            </p>
            <p className="mt-1.5 text-xs text-[var(--cos-muted)]">
              So far the agent has learned{' '}
              <span className="font-semibold text-[var(--cos-text)]">{lessons.length}</span> lesson
              {lessons.length === 1 ? '' : 's'} from past work.
            </p>
            {enoughRoi && (
              <>
                <div className="mt-2.5 flex h-10 items-end gap-0.5" aria-hidden="true">
                  {roi.sessions.map((s, i) => {
                    const max = Math.max(...roi.sessions.map((x) => x.rate), 0.01);
                    const h = Math.max(6, Math.round((s.rate / max) * 100));
                    return (
                      <span
                        key={`${s.session_id}-${i}`}
                        title={`${(s.rate * 100).toFixed(0)}% stumbles (${s.friction}/${s.total})`}
                        className="flex-1 rounded-sm"
                        style={{ height: `${h}%`, backgroundColor: roiColor(roi.trend) }}
                      />
                    );
                  })}
                </div>
                <p className="mt-1 text-[11px] text-[var(--cos-muted)]">
                  Each bar = one recent session’s stumbles (blocked actions + errors). Lower is better.
                </p>
              </>
            )}
          </section>
        )}

        {showLessons && promoted.length > 0 && (
          <section className="space-y-2.5">
            <h2 className="text-sm font-semibold text-[var(--cos-text)]">
              Graduated to rules{' '}
              <span className="font-normal text-[var(--cos-muted)]">
                ({promoted.length}) — promoted out of memory into durable rules
              </span>
            </h2>
            {promoted.map((p) => (
              <LessonCard key={p.id} p={p} slug={slug} />
            ))}
          </section>
        )}

        {showLessons && activeLessons.length > 0 && (
          <section className="space-y-3">
            <h2 className="text-sm font-semibold text-[var(--cos-text)]">
              Lessons learned{' '}
              <span className="text-[var(--cos-muted)]">({activeLessons.length})</span>
            </h2>
            {lessonGroups.map(
              (group) =>
                group.items.length > 0 && (
                  <div key={group.label} className="space-y-2.5">
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
                      {group.label}{' '}
                      <span className="font-normal normal-case">
                        ({group.items.length}) — {group.hint}
                      </span>
                    </h3>
                    {group.items.map((p) => (
                      <LessonCard key={p.id} p={p} slug={slug} />
                    ))}
                  </div>
                ),
            )}
          </section>
        )}

        {showStats && stats.length > 0 && (
          <section className="space-y-2.5">
            <h2 className="text-sm font-semibold text-[var(--cos-muted)]">
              Project stats — success rates, not lessons{' '}
              <span className="text-[var(--cos-muted)]">({stats.length})</span>
            </h2>
            {stats.map((p) => (
              <StatCard key={p.id} p={p} />
            ))}
          </section>
        )}
      </div>
    </div>
  );
}
