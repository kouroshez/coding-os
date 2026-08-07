import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { useApiGet } from "@/lib/hooks";
import { apiDelete, apiPost } from "@/lib/api-client";
import { Banner } from "@/layout/HubPrimitives";
import {
  CfgButton,
  ConfigRow,
  EmptyRow,
  Pill,
  SectionCard,
  StateRow,
  TabIntro,
  useConfigMutation,
} from "./shared";

interface AdapterModel {
  id: string;
  label: string;
  default: boolean;
}

interface AdapterRow {
  id: string;
  label: string;
  runtime: string;
  available: boolean;
  installed: boolean;
  dispatch_available: boolean;
  dispatch_declared?: boolean;
  capabilities: string[];
  health?: {
    state: string;
    failure_count: number;
    retry_after_s: number;
    probe_active: boolean;
    reason: string;
  };
  glyph?: string | null;
  models: AdapterModel[];
  mcp_config_paths: string[];
}

export function AdaptersTab() {
  const { data, isLoading, error } = useApiGet<{ adapters: AdapterRow[]; default_model: string }>(
    ["config-adapters"],
    "/api/config/adapters",
  );
  const { busyId, error: mutError, setError, run } = useConfigMutation(["config-adapters"]);
  const [showAdd, setShowAdd] = useState(false);
  if (isLoading) return <StateRow>Loading adapters…</StateRow>;
  if (error) return <StateRow>Could not load adapters: {error.message}</StateRow>;
  const all = data?.adapters ?? [];
  const installed = all.filter((a) => a.installed);
  const addable = all.filter((a) => !a.installed);
  const defaultModel = data?.default_model ?? "";
  const add = (id: string) => run(id, () => apiPost(`/api/config/adapters/${id}`));
  const remove = (id: string) => run(id, () => apiDelete(`/api/config/adapters/${id}`));
  const healthOf = (adapter: AdapterRow) =>
    adapter.health ?? {
      state: "disabled",
      failure_count: 0,
      retry_after_s: 0,
      probe_active: false,
      reason: "",
    };
  const glyphBox = (a: AdapterRow) =>
    a.glyph ? (
      <span className="inline-flex h-5 w-5 items-center justify-center rounded border border-[var(--cos-border)] font-mono text-[10px] text-[var(--cos-muted)]">
        {a.glyph}
      </span>
    ) : null;
  const adapterMeta = (a: AdapterRow) => (
    <>
      <span className="font-mono">{a.id}</span>
      {a.mcp_config_paths.length > 0 && (
        <>
          {" · MCP → "}
          <span className="font-mono">{a.mcp_config_paths.join(", ")}</span>
        </>
      )}
      {a.models.length > 0 && (
        <div className="mt-0.5">
          {a.models.map((m) => `${m.label}${m.default ? " (default)" : ""}`).join(", ")}
        </div>
      )}
      {a.dispatch_declared && (
        <div className="mt-0.5">
          dispatch · {a.dispatch_available ? healthOf(a).state : "unavailable"}
          {a.dispatch_available && healthOf(a).retry_after_s > 0
            ? ` · retry in ${healthOf(a).retry_after_s}s`
            : ""}
          {a.dispatch_available && healthOf(a).reason ? ` · ${healthOf(a).reason}` : ""}
        </div>
      )}
    </>
  );
  return (
    <>
      <TabIntro>
        The agent adapters wired for this project. The runnable one (in_process) drives Hub chat; a
        roadmap adapter is declared but not yet runnable here. Add another to run more than one
        agent side by side.
      </TabIntro>
      {mutError && (
        <Banner kind="error" onDismiss={() => setError(null)}>
          {mutError}
        </Banner>
      )}
      <SectionCard
        title="Installed"
        count={installed.length}
        action={
          addable.length > 0 ? (
            <CfgButton
              tone="primary"
              icon={<Plus size={13} aria-hidden />}
              onClick={() => setShowAdd((v) => !v)}
            >
              Add adapter
            </CfgButton>
          ) : undefined
        }
      >
        {installed.length === 0 ? (
          <EmptyRow>No adapters installed.</EmptyRow>
        ) : (
          installed.map((a) => (
            <ConfigRow
              key={a.id}
              title={
                <span className="inline-flex items-center gap-2">
                  {glyphBox(a)}
                  {a.label || a.id}
                </span>
              }
              badges={
                <span className="flex gap-1">
                  <Pill tone={a.available ? "ok" : "muted"}>{a.runtime}</Pill>
                  {a.dispatch_declared && (
                    <Pill
                      tone={
                        a.dispatch_available && healthOf(a).state === "healthy" ? "ok" : "muted"
                      }
                    >
                      {a.dispatch_available ? healthOf(a).state : "unavailable"}
                    </Pill>
                  )}
                </span>
              }
              meta={adapterMeta(a)}
              action={
                <div className="flex gap-2">
                  {a.dispatch_available && !["healthy", "disabled"].includes(healthOf(a).state) && (
                    <CfgButton
                      tone="primary"
                      busy={busyId === `${a.id}:health`}
                      onClick={() =>
                        run(`${a.id}:health`, () =>
                          apiDelete(`/api/config/adapters/${a.id}/health`),
                        )
                      }
                    >
                      Retry now
                    </CfgButton>
                  )}
                  <CfgButton
                    tone="danger"
                    busy={busyId === a.id}
                    disabled={installed.length <= 1 || (busyId !== null && busyId !== a.id)}
                    title={
                      installed.length <= 1
                        ? "A project needs at least one adapter"
                        : `Remove ${a.label || a.id}`
                    }
                    onClick={() => remove(a.id)}
                    icon={<Trash2 size={13} aria-hidden />}
                  >
                    Remove
                  </CfgButton>
                </div>
              }
            />
          ))
        )}
      </SectionCard>
      {showAdd && addable.length > 0 && (
        <SectionCard
          title="Available to add"
          count={addable.length}
          subtitle="Adding an adapter runs its install.sh and renders its per-agent surface."
        >
          {addable.map((a) => (
            <ConfigRow
              key={a.id}
              title={
                <span className="inline-flex items-center gap-2">
                  {glyphBox(a)}
                  {a.label || a.id}
                </span>
              }
              badges={<Pill tone={a.available ? "ok" : "muted"}>{a.runtime}</Pill>}
              meta={adapterMeta(a)}
              action={
                <CfgButton
                  tone="primary"
                  busy={busyId === a.id}
                  disabled={busyId !== null && busyId !== a.id}
                  onClick={() => add(a.id)}
                  icon={<Plus size={13} aria-hidden />}
                >
                  Add
                </CfgButton>
              }
            />
          ))}
        </SectionCard>
      )}
      {defaultModel && (
        <p className="mt-1 text-[11px] text-[var(--cos-faint)]">
          Default chat model:{" "}
          <span className="font-mono text-[var(--cos-muted)]">{defaultModel}</span>
        </p>
      )}
    </>
  );
}
