import { useCallback, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { PageShell, PageHeader, StatusPill } from '@/layout/HubPrimitives';
import { invalidateApiQueries, useApiGet } from '@/lib/hooks';
import { apiPatch, apiPost } from '@/lib/api-client';

interface BudgetCap {
  enabled: boolean;
  cap_usd: number;
}

interface TraceRotation {
  gzip_age_days: number;
  delete_age_days: number;
}

interface Settings {
  budget_cap: BudgetCap;
  trace_rotation: TraceRotation;
}

interface SettingsPayload {
  settings: Settings;
  env_overrides: Record<string, string>;
}

function EnvBadge({ varName, value }: { varName: string; value: string }) {
  return (
    <span
      className="ml-2 rounded border border-[var(--cos-warn)] bg-[var(--cos-warn-tint)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--cos-warn)]"
      title={`Overridden by env var: ${varName}=${value}`}
    >
      env: {varName}={value}
    </span>
  );
}

function SectionHeader({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="mb-4">
      <h2 className="text-sm font-semibold text-[var(--cos-text)]">{title}</h2>
      <p className="mt-0.5 text-xs text-[var(--cos-muted)]">{desc}</p>
    </div>
  );
}

function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-3 py-2">
      <span className="w-44 shrink-0 text-xs text-[var(--cos-muted)]">{label}</span>
      <div className="flex flex-1 flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

function NumInput({
  value,
  onChange,
  min,
  max,
  step,
  disabled,
}: {
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
}) {
  return (
    <input
      type="number"
      value={value}
      min={min}
      max={max}
      step={step ?? 1}
      disabled={disabled}
      onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
      className={[
        'w-28 rounded border border-[var(--cos-border)] bg-[var(--cos-bg)]',
        'px-2 py-1 font-mono text-xs text-[var(--cos-text)]',
        'focus:outline-none focus:ring-1 focus:ring-[var(--accent)]',
        disabled ? 'cursor-not-allowed opacity-50' : '',
      ].join(' ')}
    />
  );
}

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-xs">
      <span
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={[
          'relative inline-block h-5 w-9 shrink-0 rounded-full border transition-colors',
          checked
            ? 'border-[var(--accent)] bg-[var(--accent)]/30'
            : 'border-[var(--cos-border)] bg-[var(--cos-bg)]',
        ].join(' ')}
      >
        <span
          className={[
            'absolute top-0.5 h-4 w-4 rounded-full border transition-transform',
            checked
              ? 'translate-x-4 border-[var(--accent)] bg-[var(--accent)]'
              : 'translate-x-0.5 border-[var(--cos-border)] bg-[var(--cos-muted)]',
          ].join(' ')}
        />
      </span>
      <span className="text-[var(--cos-text)]">{label}</span>
    </label>
  );
}

interface ScheduledConfig {
  enabled: boolean;
  hour: number;
  decay_throttle_days: number;
  learn_extract_min_outcomes: number;
  responsive_extract_threshold: number;
  archive_prune_days: number;
}

interface ScheduledProject {
  slug: string;
  path: string;
  last_run_at?: string | null;
  tasks?: Record<string, unknown>;
  consecutive_failures?: number;
  disabled_reason?: string | null;
  last_error?: string | null;
}

interface ScheduledStatus {
  cron_a?: {
    installed: boolean;
    loaded: boolean;
    last_run_at?: string | null;
    next_run_at?: string | null;
    plist_path?: string;
    log_dir?: string;
  };
  projects: ScheduledProject[];
}

interface RunResult {
  slug: string;
  ran: boolean;
  summary?: Record<string, unknown> | null;
  error?: string | null;
}

interface ScheduledConfigResp {
  slug: string;
  config: ScheduledConfig;
}

// Per-project form. Keyed by slug at the call site so switching projects
// remounts it with a fresh draft hydrated from the server config.
function ScheduledConfigForm({ slug, initial }: { slug: string; initial: ScheduledConfig }) {
  const qc = useQueryClient();
  const [cfg, setCfg] = useState<ScheduledConfig>(initial);
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const save = useCallback(async () => {
    setSaving(true);
    setNote(null);
    setErr(null);
    try {
      const path = `/api/scheduled/config/${encodeURIComponent(slug)}`;
      const [res] = await apiPatch<ScheduledConfigResp>(path, cfg);
      await invalidateApiQueries(qc, path);
      setCfg(res.config);
      setNote('Scheduled config saved.');
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'save failed');
    } finally {
      setSaving(false);
    }
  }, [slug, cfg, qc]);

  return (
    <div className="mt-3">
      <div className="divide-y divide-[var(--cos-border)]">
        <FieldRow label="Enable maintenance">
          <Toggle
            checked={cfg.enabled}
            onChange={(v) => setCfg({ ...cfg, enabled: v })}
            label={cfg.enabled ? 'Enabled' : 'Disabled (nightly skips this project)'}
          />
        </FieldRow>
        <FieldRow label="Nightly hour (0–23)">
          <NumInput
            value={cfg.hour}
            onChange={(v) => setCfg({ ...cfg, hour: Math.max(0, Math.min(23, Math.round(v))) })}
            min={0}
            max={23}
            disabled={!cfg.enabled}
          />
          <span className="text-xs text-[var(--cos-muted)]">
            launchd run hour — re-run <code>make cron-install</code> to apply
          </span>
        </FieldRow>
        <FieldRow label="Decay throttle (days)">
          <NumInput
            value={cfg.decay_throttle_days}
            onChange={(v) => setCfg({ ...cfg, decay_throttle_days: Math.max(1, Math.round(v)) })}
            min={1}
            disabled={!cfg.enabled}
          />
          <span className="text-xs text-[var(--cos-muted)]">skip decay if it ran more recently</span>
        </FieldRow>
        <FieldRow label="Extract min outcomes">
          <NumInput
            value={cfg.learn_extract_min_outcomes}
            onChange={(v) =>
              setCfg({ ...cfg, learn_extract_min_outcomes: Math.max(1, Math.round(v)) })
            }
            min={1}
            disabled={!cfg.enabled}
          />
          <span className="text-xs text-[var(--cos-muted)]">total outcomes needed to extract</span>
        </FieldRow>
        <FieldRow label="Responsive threshold">
          <NumInput
            value={cfg.responsive_extract_threshold}
            onChange={(v) =>
              setCfg({ ...cfg, responsive_extract_threshold: Math.max(1, Math.round(v)) })
            }
            min={1}
            disabled={!cfg.enabled}
          />
          <span className="text-xs text-[var(--cos-muted)]">
            new outcomes before session-end extracts same-day
          </span>
        </FieldRow>
        <FieldRow label="Archive prune (days)">
          <NumInput
            value={cfg.archive_prune_days}
            onChange={(v) => setCfg({ ...cfg, archive_prune_days: Math.max(7, Math.round(v)) })}
            min={7}
            disabled={!cfg.enabled}
          />
          <span className="text-xs text-[var(--cos-muted)]">
            hard-delete dormant archived patterns older than this
          </span>
        </FieldRow>
      </div>
      {note && <p className="mt-3 text-[11px] text-[var(--cos-ok)]">{note}</p>}
      {err && <p className="mt-3 text-[11px] text-[var(--cos-err)]">{err}</p>}
      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          onClick={() => void save()}
          disabled={saving}
          className={[
            'rounded border px-4 py-2 font-mono text-xs font-semibold transition-colors',
            'border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]',
            'hover:bg-[var(--accent)]/20 disabled:cursor-not-allowed disabled:opacity-50',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]',
          ].join(' ')}
        >
          {saving ? 'saving…' : 'Save scheduled config'}
        </button>
        <button
          type="button"
          disabled={saving}
          onClick={() => {
            setCfg(initial);
            setNote(null);
            setErr(null);
          }}
          className="rounded border border-[var(--cos-border)] px-4 py-2 font-mono text-xs text-[var(--cos-muted)] transition-colors hover:border-[var(--cos-text)] hover:text-[var(--cos-text)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          Reset
        </button>
      </div>
    </div>
  );
}

function ScheduledMaintenanceSection() {
  const qc = useQueryClient();
  const { data: status } = useApiGet<ScheduledStatus>(['scheduled-status'], '/api/scheduled/status');
  const projects = status?.projects ?? [];
  const [slug, setSlug] = useState('');
  const activeSlug = slug || projects[0]?.slug || '';
  const activeProj = projects.find((p) => p.slug === activeSlug);
  const [running, setRunning] = useState(false);
  const [runNote, setRunNote] = useState<string | null>(null);

  const runNow = useCallback(async () => {
    if (!activeSlug) return;
    setRunning(true);
    setRunNote(null);
    try {
      const [res] = await apiPost<RunResult>(
        `/api/scheduled/run/${encodeURIComponent(activeSlug)}`,
      );
      await invalidateApiQueries(qc, '/api/scheduled/status');
      setRunNote(res.ran ? 'Learning loop ran.' : `Failed: ${res.error ?? 'unknown'}`);
    } catch (e) {
      setRunNote(e instanceof Error ? e.message : 'run failed');
    } finally {
      setRunning(false);
    }
  }, [activeSlug, qc]);
  const { data: cfgResp } = useApiGet<ScheduledConfigResp>(
    ['scheduled-config', activeSlug],
    `/api/scheduled/config/${encodeURIComponent(activeSlug)}`,
    undefined,
    { enabled: !!activeSlug },
  );

  return (
    <section className="rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] p-5">
      <SectionHeader
        title="Scheduled Maintenance"
        desc="Per-project cron cadence + responsive learning. Stored in .coding-os/scheduled/config.json; read by the nightly daemon and the session-end responsive extractor."
      />
      {projects.length === 0 ? (
        <p className="text-xs text-[var(--cos-muted)]">No registered projects.</p>
      ) : (
        <>
          <FieldRow label="Project">
            <select
              value={activeSlug}
              onChange={(e) => setSlug(e.target.value)}
              className="rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1 font-mono text-xs text-[var(--cos-text)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
            >
              {projects.map((p) => (
                <option key={p.slug} value={p.slug}>
                  {p.slug}
                </option>
              ))}
            </select>
          </FieldRow>
          {cfgResp?.config ? (
            <ScheduledConfigForm key={activeSlug} slug={activeSlug} initial={cfgResp.config} />
          ) : (
            <p className="mt-3 text-xs text-[var(--cos-muted)]">loading config…</p>
          )}

          <div className="mt-4 flex items-center gap-3 border-t border-[var(--cos-border)] pt-3">
            <button
              onClick={runNow}
              disabled={running || !activeSlug}
              className="rounded border border-[var(--cos-border)] px-4 py-2 font-mono text-xs text-[var(--cos-text)] transition-colors hover:border-[var(--accent)] hover:text-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {running ? 'running…' : 'Run learning loop now'}
            </button>
            <span className="font-mono text-[11px] text-[var(--cos-muted)]">
              {runNote
                ? runNote
                : activeProj?.last_run_at
                  ? `last run ${activeProj.last_run_at}` +
                    (activeProj.consecutive_failures
                      ? ` · ${activeProj.consecutive_failures} fail(s)`
                      : '')
                  : 'never run'}
            </span>
          </div>
          {status?.cron_a ? (
            <p className="mt-2 font-mono text-[11px] text-[var(--cos-muted)]">
              nightly cron: {status.cron_a.loaded ? 'loaded' : 'not loaded'}
              {status.cron_a.next_run_at ? ` · next ${status.cron_a.next_run_at}` : ''}
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}

export default function SettingsPage() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useApiGet<SettingsPayload>(
    ['settings'],
    '/api/settings',
  );

  const [saving, setSaving] = useState(false);
  const [saveNote, setSaveNote] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Local draft state — mirrors server; hydrated from API response
  const [budget, setBudget] = useState<BudgetCap | null>(null);
  const [trace, setTrace] = useState<TraceRotation | null>(null);

  // Sync draft with server data on first load (not on every refetch)
  const serverSettings = data?.settings;
  const localBudget: BudgetCap = budget ?? serverSettings?.budget_cap ?? { enabled: false, cap_usd: 5.0 };
  const localTrace: TraceRotation = trace ?? serverSettings?.trace_rotation ?? { gzip_age_days: 3, delete_age_days: 30 };
  const envOverrides = data?.env_overrides ?? {};

  const save = useCallback(async () => {
    setSaving(true);
    setSaveNote(null);
    setSaveError(null);
    try {
      const [result] = await apiPatch<SettingsPayload>('/api/settings', {
        budget_cap: localBudget,
        trace_rotation: localTrace,
      });
      await invalidateApiQueries(qc, '/api/settings');
      setBudget(result.settings.budget_cap);
      setTrace(result.settings.trace_rotation);
      setSaveNote('Settings saved.');
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'save failed');
    } finally {
      setSaving(false);
    }
  }, [localBudget, localTrace, qc]);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-[var(--cos-muted)]">
        loading…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-[var(--cos-err)]">
        {error.message}
      </div>
    );
  }

  return (
    <PageShell>
      <PageHeader
        eyebrow={<StatusPill label="settings · hub config" dotColor="bg-[var(--cos-brand-tint)]" />}
        title="Settings"
        subtitle={
          <>
            Hub-level configuration. Values stored in{' '}
            <code className="rounded bg-[var(--cos-panel)] px-1 py-0.5 text-[11px]">
              .coding-os/hub-settings.json
            </code>. Env vars take precedence when set.
          </>
        }
      />

      {saveNote && (
        <div className="mb-4 rounded border border-[var(--cos-ok)] bg-[var(--cos-ok-tint)] px-3 py-2 text-xs text-[var(--cos-ok)]">
          {saveNote}
          <button
            type="button"
            className="ml-3 underline opacity-70 hover:opacity-100"
            onClick={() => setSaveNote(null)}
          >
            dismiss
          </button>
        </div>
      )}
      {saveError && (
        <div className="mb-4 rounded border border-[var(--cos-err)] bg-[var(--cos-err-tint)] px-3 py-2 text-xs text-[var(--cos-err)]">
          {saveError}
          <button
            type="button"
            className="ml-3 underline opacity-70 hover:opacity-100"
            onClick={() => setSaveError(null)}
          >
            dismiss
          </button>
        </div>
      )}

      <div className="max-w-2xl space-y-6">
        {/* Budget Cap */}
        <section className="rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] p-5">
          <SectionHeader
            title="Daily Budget Cap"
            desc="Blocks formula dispatches (cos_dispatch_formula_run / cos_dispatch_parallel_run) when today's accumulated cost exceeds the cap. Resets at UTC midnight. Default: OFF."
          />
          <div className="divide-y divide-[var(--cos-border)]">
            <FieldRow label="Enable budget cap">
              <Toggle
                checked={localBudget.enabled}
                onChange={(v) => setBudget({ ...localBudget, enabled: v })}
                label={localBudget.enabled ? 'Enabled' : 'Disabled'}
              />
              {envOverrides['COS_DAILY_BUDGET_USD'] && (
                <EnvBadge varName="COS_DAILY_BUDGET_USD" value={envOverrides['COS_DAILY_BUDGET_USD']} />
              )}
            </FieldRow>
            <FieldRow label="Daily cap (USD)">
              <NumInput
                value={localBudget.cap_usd}
                onChange={(v) => setBudget({ ...localBudget, cap_usd: v })}
                min={0.01}
                step={0.5}
                disabled={!localBudget.enabled}
              />
              <span className="text-xs text-[var(--cos-muted)]">USD / day</span>
              {envOverrides['COS_DAILY_BUDGET_USD'] && (
                <span className="text-[10px] text-[var(--cos-warn)]">
                  env var overrides this when set
                </span>
              )}
            </FieldRow>
          </div>
          <p className="mt-3 text-[10px] leading-relaxed text-[var(--cos-muted)]">
            Override via shell:{' '}
            <code>export COS_DAILY_BUDGET_USD=5.00</code> — env var takes
            precedence over this panel setting.
          </p>
        </section>

        {/* Trace Rotation */}
        <section className="rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] p-5">
          <SectionHeader
            title="Trace Rotation"
            desc="Controls how the auto-trace-rotate.sh Stop hook manages JSONL trace files under .coding-os/<agent>/traces/."
          />
          <div className="divide-y divide-[var(--cos-border)]">
            <FieldRow label="Gzip after (days)">
              <NumInput
                value={localTrace.gzip_age_days}
                onChange={(v) => setTrace({ ...localTrace, gzip_age_days: Math.max(1, Math.round(v)) })}
                min={1}
              />
              <span className="text-xs text-[var(--cos-muted)]">
                days — compress traces older than this
              </span>
              {envOverrides['COS_TRACE_GZIP_AGE_DAYS'] && (
                <EnvBadge varName="COS_TRACE_GZIP_AGE_DAYS" value={envOverrides['COS_TRACE_GZIP_AGE_DAYS']} />
              )}
            </FieldRow>
            <FieldRow label="Delete after (days)">
              <NumInput
                value={localTrace.delete_age_days}
                onChange={(v) => setTrace({ ...localTrace, delete_age_days: Math.max(1, Math.round(v)) })}
                min={1}
              />
              <span className="text-xs text-[var(--cos-muted)]">
                days — delete compressed archives older than this
              </span>
              {envOverrides['COS_TRACE_DELETE_AGE_DAYS'] && (
                <EnvBadge varName="COS_TRACE_DELETE_AGE_DAYS" value={envOverrides['COS_TRACE_DELETE_AGE_DAYS']} />
              )}
            </FieldRow>
          </div>
          <p className="mt-3 text-[10px] leading-relaxed text-[var(--cos-muted)]">
            <strong className="text-[var(--cos-text)]">Gzip age</strong> —
            after N days, raw <code>.jsonl</code> files are compressed to{' '}
            <code>.jsonl.gz</code> to save disk.{' '}
            <strong className="text-[var(--cos-text)]">Delete age</strong> —
            after M days, <code>.jsonl.gz</code> archives are removed
            permanently. Set M &gt; N. Override via shell:{' '}
            <code>export COS_TRACE_GZIP_AGE_DAYS=3</code>,{' '}
            <code>export COS_TRACE_DELETE_AGE_DAYS=30</code>.
          </p>
        </section>

        {/* Scheduled Maintenance (per-project cron + responsive learning) */}
        <ScheduledMaintenanceSection />

        <div className="flex items-center gap-3 pt-2">
          <button
            type="button"
            onClick={() => void save()}
            disabled={saving}
            className={[
              'rounded border px-4 py-2 font-mono text-xs font-semibold transition-colors',
              'border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]',
              'hover:bg-[var(--accent)]/20 disabled:cursor-not-allowed disabled:opacity-50',
            ].join(' ')}
          >
            {saving ? 'saving…' : 'Save settings'}
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={() => {
              setBudget(serverSettings?.budget_cap ?? null);
              setTrace(serverSettings?.trace_rotation ?? null);
              setSaveNote(null);
              setSaveError(null);
            }}
            className="rounded border border-[var(--cos-border)] px-4 py-2 font-mono text-xs text-[var(--cos-muted)] transition-colors hover:border-[var(--cos-text)] hover:text-[var(--cos-text)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            Reset
          </button>
        </div>
      </div>
    </PageShell>
  );
}
