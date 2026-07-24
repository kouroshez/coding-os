import { forwardRef, useCallback, useImperativeHandle, useRef, useState } from 'react';
import type { Ref } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { PageShell, PageHeader, StatusPill } from '@/layout/HubPrimitives';
import { invalidateApiQueries, useApiGet } from '@/lib/hooks';
import { apiPatch, apiPost } from '@/lib/api-client';
import type { Adapter } from '@/features/cognition/ModelPicker';

interface BudgetCap {
  enabled: boolean;
  cap_usd: number;
}

interface TraceRotation {
  gzip_age_days: number;
  delete_age_days: number;
}

interface ModelRouting {
  enabled: boolean;
  orchestrator_model: string;
}

interface AutoSpawn {
  enabled: boolean;
}

// Masked shape returned by GET/PATCH — the raw key never crosses the wire
// after being stored (settings.py::_masked_settings).
interface ClaudeAuth {
  mode: 'subscription' | 'api_key';
  api_key_set: boolean;
  api_key_preview: string;
}

interface Settings {
  budget_cap: BudgetCap;
  trace_rotation: TraceRotation;
  model_routing: ModelRouting;
  auto_spawn: AutoSpawn;
  claude_auth: ClaudeAuth;
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
    <span className="flex items-center gap-2 text-xs">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        className={[
          'relative inline-block h-5 w-9 shrink-0 cursor-pointer rounded-full border transition-colors',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]',
          checked
            ? 'border-[var(--accent)] bg-[var(--accent)]/30'
            : 'border-[var(--cos-border)] bg-[var(--cos-bg)]',
        ].join(' ')}
      >
        <span
          aria-hidden
          className={[
            'absolute top-0.5 h-4 w-4 rounded-full border transition-transform',
            checked
              ? 'translate-x-4 border-[var(--accent)] bg-[var(--accent)]'
              : 'translate-x-0.5 border-[var(--cos-border)] bg-[var(--cos-muted)]',
          ].join(' ')}
        />
      </button>
      <span className="text-[var(--cos-text)]">{label}</span>
    </span>
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
export interface ScheduledFormHandle {
  saveIfDirty: () => Promise<void>;
}

const ScheduledConfigForm = forwardRef(function ScheduledConfigForm(
  { slug, initial }: { slug: string; initial: ScheduledConfig },
  ref: Ref<ScheduledFormHandle>,
) {
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

  // Lets the page-level "Save settings" flush pending scheduled edits too, so
  // there is a single save flow — the dedicated button stays for explicit saves.
  useImperativeHandle(
    ref,
    () => ({
      saveIfDirty: async () => {
        if (JSON.stringify(cfg) !== JSON.stringify(initial)) await save();
      },
    }),
    [cfg, initial, save],
  );

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
});

function ScheduledMaintenanceSection({ formRef }: { formRef: Ref<ScheduledFormHandle> }) {
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
            <ScheduledConfigForm ref={formRef} key={activeSlug} slug={activeSlug} initial={cfgResp.config} />
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

function ModelRoutingSection({
  routing,
  onChange,
}: {
  routing: ModelRouting;
  onChange: (next: ModelRouting) => void;
}) {
  // Producer: /api/config/adapters (adapter.yaml::models SSOT) — same payload
  // the chat ModelPicker consumes; field names verified against config.py.
  const { data } = useApiGet<{ adapters: Adapter[]; default_model: string; count: number }>(
    ['config-adapters'],
    '/api/config/adapters',
  );
  const availableAdapters = (data?.adapters ?? []).filter((a) => a.available && a.models.length > 0);

  return (
    <section className="rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] p-5">
      <SectionHeader
        title="Model Routing (Auto)"
        desc="When enabled, the chat model picker offers an Auto option: the orchestrator model classifies each prompt and hands the session to the routed model. Disabled keeps the feature fully inert — no Auto option, no injected context, no dispatch change. Default: OFF."
      />
      <div className="divide-y divide-[var(--cos-border)]">
        <FieldRow label="Enable auto routing">
          <Toggle
            checked={routing.enabled}
            onChange={(v) => onChange({ ...routing, enabled: v })}
            label={routing.enabled ? 'Enabled' : 'Disabled'}
          />
        </FieldRow>
        <FieldRow label="Orchestrator model">
          <select
            value={routing.orchestrator_model}
            onChange={(e) => onChange({ ...routing, orchestrator_model: e.target.value })}
            disabled={!routing.enabled}
            className="rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1.5 font-mono text-xs text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <option value="">adapter default</option>
            {availableAdapters.map((adapter) => (
              <optgroup key={adapter.id} label={adapter.label}>
                {adapter.models.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.label}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
          {routing.enabled && availableAdapters.length === 0 && (
            <span className="text-[10px] text-[var(--cos-warn)]">
              no adapter models found — check /api/config/adapters
            </span>
          )}
        </FieldRow>
      </div>
      <p className="mt-3 text-[10px] leading-relaxed text-[var(--cos-muted)]">
        Models come from each adapter&apos;s <code>adapter.yaml::models</code>{' '}
        registry — adding a model is a yaml edit, never a UI or code change.
        CLI/VSCode sessions honor the same toggle via the routing hook.
      </p>
    </section>
  );
}

function ClaudeAuthSection({
  auth,
  onModeChange,
  apiKeyDraft,
  onApiKeyDraftChange,
}: {
  auth: ClaudeAuth;
  onModeChange: (mode: ClaudeAuth['mode']) => void;
  apiKeyDraft: string | null;
  onApiKeyDraftChange: (v: string | null) => void;
}) {
  const modeButton = (mode: ClaudeAuth['mode'], label: string) => (
    <button
      type="button"
      onClick={() => onModeChange(mode)}
      aria-pressed={auth.mode === mode}
      className={[
        'rounded border px-3 py-1.5 font-mono text-xs transition-colors focus-visible:ring-2 focus-visible:ring-[var(--accent)]',
        auth.mode === mode
          ? 'border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]'
          : 'border-[var(--cos-border)] text-[var(--cos-muted)] hover:border-[var(--cos-text)] hover:text-[var(--cos-text)]',
      ].join(' ')}
    >
      {label}
    </button>
  );

  return (
    <section className="rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] p-5">
      <SectionHeader
        title="Claude Auth"
        desc="How every Claude dispatch (chat + formula) authenticates. Subscription (default) uses the Claude Code CLI's own login — the common case for Pro/Max/Team users. API Key forwards a key you supply here as ANTHROPIC_API_KEY, which takes precedence over the CLI's login for this project."
      />
      <div className="divide-y divide-[var(--cos-border)]">
        <FieldRow label="Auth mode">
          <div className="flex gap-2">
            {modeButton('subscription', 'Subscription (OAuth)')}
            {modeButton('api_key', 'API Key')}
          </div>
        </FieldRow>
        {auth.mode === 'api_key' && (
          <FieldRow label="API key">
            <input
              type="password"
              autoComplete="off"
              value={apiKeyDraft ?? ''}
              onChange={(e) => onApiKeyDraftChange(e.target.value)}
              placeholder={
                auth.api_key_set ? `configured (${auth.api_key_preview}) — leave blank to keep` : 'sk-ant-...'
              }
              className="w-72 rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1.5 font-mono text-xs text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
            />
            {auth.api_key_set && (
              <button
                type="button"
                onClick={() => onApiKeyDraftChange('')}
                className="text-[10px] text-[var(--cos-muted)] underline hover:text-[var(--cos-warn)]"
              >
                clear stored key
              </button>
            )}
            {apiKeyDraft === '' && auth.api_key_set && (
              <span className="text-[10px] text-[var(--cos-warn)]">will clear on save</span>
            )}
          </FieldRow>
        )}
      </div>
      <p className="mt-3 text-[10px] leading-relaxed text-[var(--cos-muted)]">
        The key is write-only past this form — reads only ever show{' '}
        <code>api_key_set</code> + a last-4 preview, never the raw value.
        Switching back to Subscription does not delete a stored key; it
        just stops using it for this project.
      </p>
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
  const scheduledFormRef = useRef<ScheduledFormHandle>(null);

  // Local draft state — mirrors server; hydrated from API response
  const [budget, setBudget] = useState<BudgetCap | null>(null);
  const [trace, setTrace] = useState<TraceRotation | null>(null);
  const [routing, setRouting] = useState<ModelRouting | null>(null);
  const [autoSpawn, setAutoSpawn] = useState<AutoSpawn | null>(null);
  const [claudeAuth, setClaudeAuth] = useState<ClaudeAuth | null>(null);
  // null = no change queued (omit api_key from the PATCH entirely); '' = explicit
  // clear; non-empty = set/replace. Never pre-filled from the masked GET response.
  const [claudeAuthApiKeyDraft, setClaudeAuthApiKeyDraft] = useState<string | null>(null);

  // Sync draft with server data on first load (not on every refetch)
  const serverSettings = data?.settings;
  const localBudget: BudgetCap = budget ?? serverSettings?.budget_cap ?? { enabled: false, cap_usd: 5.0 };
  const localTrace: TraceRotation = trace ?? serverSettings?.trace_rotation ?? { gzip_age_days: 3, delete_age_days: 30 };
  const localRouting: ModelRouting = routing ?? serverSettings?.model_routing ?? { enabled: false, orchestrator_model: '' };
  const localAutoSpawn: AutoSpawn = autoSpawn ?? serverSettings?.auto_spawn ?? { enabled: false };
  const localClaudeAuth: ClaudeAuth =
    claudeAuth ?? serverSettings?.claude_auth ?? { mode: 'subscription', api_key_set: false, api_key_preview: '' };
  const envOverrides = data?.env_overrides ?? {};

  const save = useCallback(async () => {
    setSaving(true);
    setSaveNote(null);
    setSaveError(null);
    try {
      const [result] = await apiPatch<SettingsPayload>('/api/settings', {
        budget_cap: localBudget,
        trace_rotation: localTrace,
        model_routing: localRouting,
        auto_spawn: localAutoSpawn,
        claude_auth: {
          mode: localClaudeAuth.mode,
          // Omit the key entirely unless the user actually typed/cleared it —
          // exclude_unset on the backend then preserves whatever is stored.
          ...(claudeAuthApiKeyDraft !== null ? { api_key: claudeAuthApiKeyDraft } : {}),
        },
      });
      await invalidateApiQueries(qc, '/api/settings');
      setBudget(result.settings.budget_cap);
      setTrace(result.settings.trace_rotation);
      setRouting(result.settings.model_routing);
      setAutoSpawn(result.settings.auto_spawn);
      setClaudeAuth(result.settings.claude_auth);
      setClaudeAuthApiKeyDraft(null);
      // Single save flow: also flush pending Scheduled-Maintenance edits.
      await scheduledFormRef.current?.saveIfDirty();
      setSaveNote('Settings saved.');
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'save failed');
    } finally {
      setSaving(false);
    }
  }, [localBudget, localTrace, localRouting, localClaudeAuth, claudeAuthApiKeyDraft, qc]);

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

        {/* Model Routing (Auto) */}
        <ModelRoutingSection routing={localRouting} onChange={setRouting} />

        {/* Board drag auto-spawn */}
        <section className="rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] p-5">
          <SectionHeader
            title="Board Auto-Spawn"
            desc="When enabled, dragging a task from ICE BOX to IN PROGRESS on the board dispatches an implementer agent session on that task automatically — the card's live pip lights up and the spawn outcome lands in the stream as a dispatch row. Agent-initiated moves never trigger it. Default: OFF."
          />
          <div className="divide-y divide-[var(--cos-border)]">
            <FieldRow label="Spawn agent on drag">
              <Toggle
                checked={localAutoSpawn.enabled}
                onChange={(v) => setAutoSpawn({ enabled: v })}
                label={localAutoSpawn.enabled ? 'Enabled' : 'Disabled'}
              />
            </FieldRow>
          </div>
        </section>

        {/* Claude Auth (subscription vs API key) */}
        <ClaudeAuthSection
          auth={localClaudeAuth}
          onModeChange={(mode) => setClaudeAuth({ ...localClaudeAuth, mode })}
          apiKeyDraft={claudeAuthApiKeyDraft}
          onApiKeyDraftChange={setClaudeAuthApiKeyDraft}
        />

        {/* Scheduled Maintenance (per-project cron + responsive learning) */}
        <ScheduledMaintenanceSection formRef={scheduledFormRef} />

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
              setRouting(serverSettings?.model_routing ?? null);
              setAutoSpawn(serverSettings?.auto_spawn ?? null);
              setClaudeAuth(serverSettings?.claude_auth ?? null);
              setClaudeAuthApiKeyDraft(null);
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
