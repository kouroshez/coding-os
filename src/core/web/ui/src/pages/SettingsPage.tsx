import { useCallback, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { PageShell, PageHeader, StatusPill } from '@/layout/HubPrimitives';
import { invalidateApiQueries, useApiGet } from '@/lib/hooks';
import { apiPatch } from '@/lib/api-client';

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
      className="ml-2 rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 font-mono text-[10px] text-amber-400"
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
      <div className="flex h-full items-center justify-center text-sm text-rose-400">
        {error.message}
      </div>
    );
  }

  return (
    <PageShell>
      <PageHeader
        eyebrow={<StatusPill label="settings · hub config" dotColor="bg-violet-400" />}
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
        <div className="mb-4 rounded border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
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
        <div className="mb-4 rounded border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
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
                <span className="text-[10px] text-amber-400">
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
