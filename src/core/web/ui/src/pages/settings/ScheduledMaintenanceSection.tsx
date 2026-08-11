import { forwardRef, useCallback, useImperativeHandle, useState } from "react";
import type { Ref } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { invalidateApiQueries, useApiGet } from "@/lib/hooks";
import { apiPatch, apiPost, type ApiPath, type paths } from "@/lib/api-client";
import { FieldRow, NumInput, SectionHeader, Toggle } from "./SettingsPrimitives";

interface ScheduledConfig {
  enabled: boolean;
  hour: number;
  decay_throttle_days: number;
  learn_extract_min_outcomes: number;
  responsive_extract_threshold: number;
  archive_prune_days: number;
}

// Derived from the OpenAPI schema (routes/scheduled.py declares response_models
// for these two) so a producer rename fails typecheck here. The config routes
// below still return a bare dict, so their shape stays hand-written.
type ScheduledStatus =
  paths["/api/scheduled/status"]["get"]["responses"]["200"]["content"]["application/json"];
type ScheduledProject = ScheduledStatus["projects"][number];
type RunResult =
  paths["/api/scheduled/run/{slug}"]["post"]["responses"]["200"]["content"]["application/json"];

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
      const path: ApiPath = `/api/scheduled/config/${encodeURIComponent(slug)}`;
      const [res] = await apiPatch<ScheduledConfigResp>(path, cfg);
      await invalidateApiQueries(qc, path);
      setCfg(res.config);
      setNote("Scheduled config saved.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "save failed");
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
            label={cfg.enabled ? "Enabled" : "Disabled (nightly skips this project)"}
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
          <span className="text-xs text-[var(--cos-muted)]">
            skip decay if it ran more recently
          </span>
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
            "rounded border px-4 py-2 font-mono text-xs font-semibold transition-colors",
            "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]",
            "hover:bg-[var(--accent)]/20 disabled:cursor-not-allowed disabled:opacity-50",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
          ].join(" ")}
        >
          {saving ? "saving…" : "Save scheduled config"}
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

export function ScheduledMaintenanceSection({ formRef }: { formRef: Ref<ScheduledFormHandle> }) {
  const qc = useQueryClient();
  const { data: status } = useApiGet<ScheduledStatus>(
    ["scheduled-status"],
    "/api/scheduled/status",
  );
  // The producer types slug as nullable (scheduled.py::ProjectScheduled); a row
  // without one can't be selected or run, so it never reaches the picker.
  const projects = (status?.projects ?? []).filter(
    (p): p is ScheduledProject & { slug: string } => !!p.slug,
  );
  const [slug, setSlug] = useState("");
  const activeSlug = slug || projects[0]?.slug || "";
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
      await invalidateApiQueries(qc, "/api/scheduled/status");
      setRunNote(res.ran ? "Learning loop ran." : `Failed: ${res.error ?? "unknown"}`);
    } catch (e) {
      setRunNote(e instanceof Error ? e.message : "run failed");
    } finally {
      setRunning(false);
    }
  }, [activeSlug, qc]);
  const { data: cfgResp } = useApiGet<ScheduledConfigResp>(
    ["scheduled-config", activeSlug],
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
            <ScheduledConfigForm
              ref={formRef}
              key={activeSlug}
              slug={activeSlug}
              initial={cfgResp.config}
            />
          ) : (
            <p className="mt-3 text-xs text-[var(--cos-muted)]">loading config…</p>
          )}

          <div className="mt-4 flex items-center gap-3 border-t border-[var(--cos-border)] pt-3">
            <button
              onClick={runNow}
              disabled={running || !activeSlug}
              className="rounded border border-[var(--cos-border)] px-4 py-2 font-mono text-xs text-[var(--cos-text)] transition-colors hover:border-[var(--accent)] hover:text-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {running ? "running…" : "Run learning loop now"}
            </button>
            <span className="font-mono text-[11px] text-[var(--cos-muted)]">
              {runNote
                ? runNote
                : activeProj?.last_run_at
                  ? `last run ${activeProj.last_run_at}` +
                    (activeProj.consecutive_failures
                      ? ` · ${activeProj.consecutive_failures} fail(s)`
                      : "")
                  : "never run"}
            </span>
          </div>
          {status?.cron_a ? (
            <p className="mt-2 font-mono text-[11px] text-[var(--cos-muted)]">
              nightly cron: {status.cron_a.loaded ? "loaded" : "not loaded"}
              {status.cron_a.next_run_at ? ` · next ${status.cron_a.next_run_at}` : ""}
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}
