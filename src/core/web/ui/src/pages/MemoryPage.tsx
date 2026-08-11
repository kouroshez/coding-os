import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { ApiError, apiGet, apiPost } from '@/lib/api-client';
// Field names mirror src/core/web/routes/patterns.py::_COLUMNS + the computed
// `tier` field (api-contract-discipline — the producer is the source of truth).
import type { PatternRow, PatternsData, RoiData, RunResp } from './memory/memory-types';
import {
  isStat,
  roiColor,
  roiHeadline,
  roiSentence,
  splitLesson,
} from './memory/memory-format';
import { LessonCard, StatCard } from './memory/MemoryCards';

// Re-exported for MemoryPage.test.ts, which imports it from here.
export { splitLesson };

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
    apiGet<PatternsData>('/api/patterns')
      .then(([data]) => {
        if (cancelled) return;
        setPatterns(data.patterns ?? []);
        setError('');
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : String(e));
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
    apiGet<{ slug: string; run_at?: string | null }>(
      `/api/scheduled/project/${encodeURIComponent(slug)}`,
    )
      .then(([d]) => {
        if (!cancelled && d) setLastRun(d.run_at ?? null);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [slug, reloadCounter]);

  // Learning effectiveness: friction-per-session trend (does it go down over time?).
  useEffect(() => {
    let cancelled = false;
    apiGet<RoiData>('/api/patterns/roi')
      .then(([d]) => {
        if (!cancelled && d) setRoi(d);
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
      const [d] = await apiPost<RunResp>(`/api/scheduled/run/${encodeURIComponent(slug)}`);
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
              <LessonCard key={p.id} p={p} />
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
                      <LessonCard key={p.id} p={p} />
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
