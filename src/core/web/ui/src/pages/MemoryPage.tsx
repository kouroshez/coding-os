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
// Plain-language read-out — celebrate the win, don't just draw a slope (XAI).
function roiSentence(trend: string): string {
  if (trend === 'improving') return 'The agent is hitting fewer repeat mistakes lately — learning is paying off.';
  if (trend === 'worsening') return 'Friction ticked up recently — worth a look at what changed.';
  return 'Friction is holding steady across recent sessions.';
}

function api(slug: string | undefined, path: string): string {
  const base = slug ? `/api/p/${slug}` : '/api';
  return `${base}${path}`;
}

// Confidence tier → colour. Meaning, not decoration. (See learning-extraction.md.)
function tierStyle(tier: string): { bg: string; fg: string } {
  if (tier === 'Trusted') return { bg: 'var(--cos-ok-tint)', fg: 'var(--cos-ok)' };
  if (tier === 'Fading') return { bg: 'var(--cos-warn-tint)', fg: 'var(--cos-warn)' };
  return { bg: 'var(--cos-overlay)', fg: 'var(--cos-muted)' }; // Forming
}

// 'stat' rows are success-rate baselines (observability) — shown separately,
// never as a learning. Everything else is a belief/lesson.
function isStat(p: PatternRow): boolean {
  return p.memory_type === 'stat';
}

// Producer lesson format: "Recurring <kind> (N occurrences): <situation> → <action>".
// L1 = situation (what went wrong), L2 = action (what to do). Fallback: whole text.
function splitLesson(pattern: string): { situation: string; action: string | null } {
  const m = pattern.match(/^Recurring .*?\(\d+ occurrences?\):\s*([\s\S]*?)\s*→\s*([\s\S]*)$/);
  if (m) return { situation: m[1].trim(), action: m[2].trim() };
  return { situation: pattern, action: null };
}

// L1+L2+L3 progressive-disclosure card with 👍/👎 feedback (closes the loop).
function LessonCard({ p, slug }: { p: PatternRow; slug: string | undefined }) {
  const [expanded, setExpanded] = useState(false);
  const [voted, setVoted] = useState<null | 'up' | 'down'>(null);
  const [busy, setBusy] = useState(false);
  const { situation, action } = splitLesson(p.pattern);
  const tier = p.tier || 'Forming';
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
            tier === 'Trusted'
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

  const lessons = patterns.filter((p) => !isStat(p));
  const stats = patterns.filter(isStat);
  const showLessons = view !== 'stats';
  const showStats = view !== 'lessons';

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

        {roi && roi.sessions.length >= 2 && (
          <section className="rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-[var(--cos-text)]">Is it working?</h2>
              <span className="text-xs font-medium" style={{ color: roiColor(roi.trend) }}>
                {roi.trend === 'improving' ? '↓' : roi.trend === 'worsening' ? '↑' : '→'}{' '}
                {roi.trend}
              </span>
            </div>
            <p className="mt-1 text-xs text-[var(--cos-muted)]">{roiSentence(roi.trend)}</p>
            <div className="mt-2 flex h-10 items-end gap-0.5" aria-hidden="true">
              {roi.sessions.map((s, i) => {
                const max = Math.max(...roi.sessions.map((x) => x.rate), 0.01);
                const h = Math.max(6, Math.round((s.rate / max) * 100));
                return (
                  <span
                    key={`${s.session_id}-${i}`}
                    title={`${(s.rate * 100).toFixed(0)}% friction (${s.friction}/${s.total})`}
                    className="flex-1 rounded-sm"
                    style={{ height: `${h}%`, backgroundColor: roiColor(roi.trend) }}
                  />
                );
              })}
            </div>
            <p className="mt-1 text-[11px] text-[var(--cos-muted)]">
              Each bar = one recent session’s friction rate (blocks + errors). Lower is better.
            </p>
          </section>
        )}

        {showLessons && lessons.length > 0 && (
          <section className="space-y-2.5">
            <h2 className="text-sm font-semibold text-[var(--cos-text)]">
              Lessons learned <span className="text-[var(--cos-muted)]">({lessons.length})</span>
            </h2>
            {lessons.map((p) => (
              <LessonCard key={p.id} p={p} slug={slug} />
            ))}
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
