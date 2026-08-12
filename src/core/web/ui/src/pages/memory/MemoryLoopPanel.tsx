import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { apiPost, type ApiPath } from '@/lib/api-client';
import { invalidateApiQueries, useApiGet } from '@/lib/hooks';
import { CfgButton } from '@/features/config/shared';
import { Banner } from '@/layout/HubPrimitives';
import type { RunResp, ScheduledState } from './memory-types';
import { dateLabel } from './memory-format';

// The nightly loop is what mints new lessons. Its last run carries a per-task
// result map, and `learn_extract` is the row that answers "why did nothing new
// appear?" — so it is shown rather than discarded.
function taskLine(state: ScheduledState | undefined): string | null {
  const lx = state?.tasks?.learn_extract;
  if (!lx?.status) return null;
  const reason = lx.reason ? ` — ${lx.reason}` : '';
  return `Last extraction: ${lx.status}${reason}`;
}

export function MemoryLoopPanel({ slug }: { slug: string | undefined }) {
  const qc = useQueryClient();
  const [running, setRunning] = useState(false);
  const [runMsg, setRunMsg] = useState('');
  const [runFailed, setRunFailed] = useState(false);
  const path: ApiPath = `/api/scheduled/project/${encodeURIComponent(slug ?? '')}`;
  const scheduled = useApiGet<ScheduledState>(['scheduled', slug ?? ''], path, undefined, {
    enabled: !!slug,
  });
  const state = scheduled.data;

  async function runLoop(): Promise<void> {
    if (!slug || running) return;
    setRunning(true);
    setRunMsg('');
    setRunFailed(false);
    try {
      const runPath: ApiPath = `/api/scheduled/run/${encodeURIComponent(slug)}`;
      const [d] = await apiPost<RunResp>(runPath);
      const lx = d?.summary?.tasks?.learn_extract;
      if (d?.ran && lx?.status === 'skipped') {
        setRunMsg(`Ran — extraction skipped${lx.reason ? ` (${lx.reason})` : ''}.`);
      } else if (d?.ran) {
        setRunMsg('Ran — see the last-run detail below.');
      } else {
        setRunFailed(true);
        setRunMsg(d?.error ?? 'the loop reported no run and no error');
      }
      await invalidateApiQueries(qc, '/api/patterns');
      await invalidateApiQueries(qc, '/api/patterns/roi');
      await invalidateApiQueries(qc, path);
    } catch (err) {
      setRunFailed(true);
      setRunMsg(err instanceof Error ? err.message : 'run failed');
    } finally {
      setRunning(false);
    }
  }

  const extraction = taskLine(state);
  const failures = state?.consecutive_failures ?? 0;

  return (
    <section
      aria-labelledby="memory-loop-heading"
      className="mb-5 rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/40 px-4 py-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 id="memory-loop-heading" className="text-sm font-semibold text-[var(--cos-text)]">
            Learning loop
          </h2>
          <p className="mt-0.5 text-[11px] leading-relaxed text-[var(--cos-faint)]">
            Distils new lessons from finished work (decay · extract · digest). Runs nightly, or on
            demand here.
          </p>
        </div>
        <CfgButton tone="primary" onClick={runLoop} busy={running} disabled={!slug || running}>
          {running ? 'Running…' : 'Run learning loop now'}
        </CfgButton>
      </div>

      <div className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1 text-[12px] text-[var(--cos-muted)]">
        {scheduled.isLoading ? (
          <span>Loading loop status…</span>
        ) : (
          <>
            <span>
              Last run: <span className="text-[var(--cos-text)]">{dateLabel(state?.run_at)}</span>
            </span>
            {extraction && <span>{extraction}</span>}
            {failures > 0 && (
              <span className="text-[var(--cos-warn)] tabular-nums">
                {failures} consecutive failure{failures === 1 ? '' : 's'}
              </span>
            )}
          </>
        )}
      </div>

      {runMsg && (
        <p
          role="status"
          className={`mt-2 text-[12px] ${runFailed ? 'text-[var(--cos-err)]' : 'text-[var(--cos-ok)]'}`}
        >
          {runMsg}
        </p>
      )}

      {scheduled.error && (
        <div className="mt-2">
          <Banner kind="error">Loop status unavailable: {scheduled.error.message}</Banner>
        </div>
      )}
      {state?.error && (
        <div className="mt-2">
          <Banner kind="error">{state.error}</Banner>
        </div>
      )}
      {state?.last_error && (
        <div className="mt-2">
          <Banner kind="error">Last run error: {state.last_error}</Banner>
        </div>
      )}
    </section>
  );
}
