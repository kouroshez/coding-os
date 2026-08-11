import { useCallback, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { PageShell, PageHeader, StatusPill } from "@/layout/HubPrimitives";
import { invalidateApiQueries, useApiGet } from "@/lib/hooks";
import { apiPatch } from "@/lib/api-client";
import type {
  AutoSpawn,
  BudgetCap,
  ClaudeAuth,
  ModelRouting,
  SettingsPayload,
  TraceRotation,
} from "./settings/settings-types";
import { normalizeModelRouting } from "./settings/settings-types";
import {
  EnvBadge,
  FieldRow,
  NumInput,
  SectionHeader,
  Toggle,
} from "./settings/SettingsPrimitives";
import { ModelRoutingSection } from "./settings/ModelRoutingSection";
import { ClaudeAuthSection } from "./settings/ClaudeAuthSection";
import { ScheduledMaintenanceSection } from "./settings/ScheduledMaintenanceSection";
import type { ScheduledFormHandle } from "./settings/ScheduledMaintenanceSection";

// Re-exported for SettingsPage.test.tsx, which imports both from here.
export { normalizeModelRouting, ModelRoutingSection };

export default function SettingsPage() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useApiGet<SettingsPayload>(["settings"], "/api/settings");

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
  const localBudget: BudgetCap = budget ??
    serverSettings?.budget_cap ?? { enabled: false, cap_usd: 5.0 };
  const localTrace: TraceRotation = trace ??
    serverSettings?.trace_rotation ?? { gzip_age_days: 3, delete_age_days: 30 };
  const localRouting = normalizeModelRouting(routing ?? serverSettings?.model_routing);
  const localAutoSpawn: AutoSpawn = autoSpawn ?? serverSettings?.auto_spawn ?? { enabled: false };
  const localClaudeAuth: ClaudeAuth = claudeAuth ??
    serverSettings?.claude_auth ?? {
      mode: "subscription",
      api_key_set: false,
      api_key_preview: "",
    };
  const envOverrides = data?.env_overrides ?? {};

  const save = useCallback(async () => {
    setSaving(true);
    setSaveNote(null);
    setSaveError(null);
    try {
      const [result] = await apiPatch<SettingsPayload>("/api/settings", {
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
      await invalidateApiQueries(qc, "/api/settings");
      setBudget(result.settings.budget_cap);
      setTrace(result.settings.trace_rotation);
      setRouting(normalizeModelRouting(result.settings.model_routing));
      setAutoSpawn(result.settings.auto_spawn);
      setClaudeAuth(result.settings.claude_auth);
      setClaudeAuthApiKeyDraft(null);
      // Single save flow: also flush pending Scheduled-Maintenance edits.
      await scheduledFormRef.current?.saveIfDirty();
      setSaveNote("Settings saved.");
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "save failed");
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
        eyebrow={
          <StatusPill label="settings · project policy" dotColor="bg-[var(--cos-brand-tint)]" />
        }
        title="Settings"
        subtitle={
          <>
            Project configuration shared by Hub, CLI, and MCP. Values stored in{" "}
            <code className="rounded bg-[var(--cos-panel)] px-1 py-0.5 text-[11px]">
              .coding-os/hub-settings.json
            </code>
            . Env vars take precedence when set.
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
                label={localBudget.enabled ? "Enabled" : "Disabled"}
              />
              {envOverrides["COS_DAILY_BUDGET_USD"] && (
                <EnvBadge
                  varName="COS_DAILY_BUDGET_USD"
                  value={envOverrides["COS_DAILY_BUDGET_USD"]}
                />
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
              {envOverrides["COS_DAILY_BUDGET_USD"] && (
                <span className="text-[10px] text-[var(--cos-warn)]">
                  env var overrides this when set
                </span>
              )}
            </FieldRow>
          </div>
          <p className="mt-3 text-[10px] leading-relaxed text-[var(--cos-muted)]">
            Override via shell: <code>export COS_DAILY_BUDGET_USD=5.00</code> — env var takes
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
                onChange={(v) =>
                  setTrace({ ...localTrace, gzip_age_days: Math.max(1, Math.round(v)) })
                }
                min={1}
              />
              <span className="text-xs text-[var(--cos-muted)]">
                days — compress traces older than this
              </span>
              {envOverrides["COS_TRACE_GZIP_AGE_DAYS"] && (
                <EnvBadge
                  varName="COS_TRACE_GZIP_AGE_DAYS"
                  value={envOverrides["COS_TRACE_GZIP_AGE_DAYS"]}
                />
              )}
            </FieldRow>
            <FieldRow label="Delete after (days)">
              <NumInput
                value={localTrace.delete_age_days}
                onChange={(v) =>
                  setTrace({ ...localTrace, delete_age_days: Math.max(1, Math.round(v)) })
                }
                min={1}
              />
              <span className="text-xs text-[var(--cos-muted)]">
                days — delete compressed archives older than this
              </span>
              {envOverrides["COS_TRACE_DELETE_AGE_DAYS"] && (
                <EnvBadge
                  varName="COS_TRACE_DELETE_AGE_DAYS"
                  value={envOverrides["COS_TRACE_DELETE_AGE_DAYS"]}
                />
              )}
            </FieldRow>
          </div>
          <p className="mt-3 text-[10px] leading-relaxed text-[var(--cos-muted)]">
            <strong className="text-[var(--cos-text)]">Gzip age</strong> — after N days, raw{" "}
            <code>.jsonl</code> files are compressed to <code>.jsonl.gz</code> to save disk.{" "}
            <strong className="text-[var(--cos-text)]">Delete age</strong> — after M days,{" "}
            <code>.jsonl.gz</code> archives are removed permanently. Set M &gt; N. Override via
            shell: <code>export COS_TRACE_GZIP_AGE_DAYS=3</code>,{" "}
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
                label={localAutoSpawn.enabled ? "Enabled" : "Disabled"}
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
              "rounded border px-4 py-2 font-mono text-xs font-semibold transition-colors",
              "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]",
              "hover:bg-[var(--accent)]/20 disabled:cursor-not-allowed disabled:opacity-50",
            ].join(" ")}
          >
            {saving ? "saving…" : "Save settings"}
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
