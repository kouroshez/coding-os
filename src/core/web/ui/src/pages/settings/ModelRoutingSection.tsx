import { useApiGet } from "@/lib/hooks";
import type { Adapter } from "@/features/cognition/ModelPicker";
import type { AdapterTarget, ModelRouting } from "./settings-types";
import { FieldRow, NumInput, SectionHeader, Toggle } from "./SettingsPrimitives";

export function ModelRoutingSection({
  routing,
  onChange,
}: {
  routing: ModelRouting;
  onChange: (next: ModelRouting) => void;
}) {
  // Producer: /api/config/adapters (adapter.yaml::models SSOT) — same payload
  // the chat ModelPicker consumes; field names verified against config.py.
  const { data } = useApiGet<{ adapters: Adapter[]; default_model: string; count: number }>(
    ["config-adapters"],
    "/api/config/adapters",
  );
  const { data: roleData } = useApiGet<{ roles: string[] }>(
    ["cognition-roles"],
    "/api/cognition/roles",
  );
  const availableAdapters = (data?.adapters ?? []).filter(
    (a) => a.installed && a.dispatch_available,
  );
  const selectClass =
    "rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1.5 font-mono text-xs text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-50";
  const updateTarget = (role: string | null, patch: Partial<AdapterTarget>) => {
    if (role === null) {
      onChange({ ...routing, orchestrator: { ...routing.orchestrator, ...patch } });
      return;
    }
    const current = routing.roles[role] ?? { adapter: "", model: "", effort: "" };
    onChange({ ...routing, roles: { ...routing.roles, [role]: { ...current, ...patch } } });
  };
  const targetControls = (role: string | null, target: AdapterTarget) => {
    const knownAdapter = availableAdapters.find((item) => item.id === target.adapter);
    const implicitAdapter = availableAdapters.length === 1 ? availableAdapters[0] : undefined;
    // A saved target whose adapter was uninstalled (or whose runtime went away)
    // still renders its own value: a blank control reads as "nothing is
    // configured", which is the opposite of the truth and hides the outage.
    const staleAdapter = target.adapter !== "" && knownAdapter === undefined;
    const adapter = knownAdapter ?? (target.adapter === "" ? implicitAdapter : undefined);
    const models = adapter?.models ?? [];
    const efforts = adapter?.efforts ?? [];
    // An adapter that selects models but publishes no catalog forwards any
    // string — offer a text field rather than an empty, unusable select.
    const freeformModel =
      adapter !== undefined &&
      models.length === 0 &&
      (adapter.capabilities ?? []).includes("model_selection");
    const staleOption = (value: string, known: boolean) =>
      value !== "" && !known ? <option value={value}>{value} — unavailable</option> : null;
    return (
      <div className="flex flex-wrap gap-2">
        {implicitAdapter && !staleAdapter ? (
          <span className="rounded border border-[var(--cos-border)] px-2 py-1.5 font-mono text-xs text-[var(--cos-muted)]">
            {implicitAdapter.label}
          </span>
        ) : (
          <select
            aria-label={`${role ?? "orchestrator"} adapter`}
            value={target.adapter}
            onChange={(event) =>
              updateTarget(role, { adapter: event.target.value, model: "", effort: "" })
            }
            className={selectClass}
          >
            <option value="">current adapter</option>
            {availableAdapters.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
            {staleOption(target.adapter, !staleAdapter)}
          </select>
        )}
        {freeformModel ? (
          <input
            aria-label={`${role ?? "orchestrator"} model`}
            value={target.model}
            onChange={(event) => updateTarget(role, { model: event.target.value })}
            placeholder="adapter default"
            className={selectClass}
          />
        ) : (
          <select
            aria-label={`${role ?? "orchestrator"} model`}
            value={target.model}
            onChange={(event) => updateTarget(role, { model: event.target.value })}
            className={selectClass}
          >
            <option value="">adapter default</option>
            {models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.label}
              </option>
            ))}
            {staleOption(
              target.model,
              models.some((model) => model.id === target.model),
            )}
          </select>
        )}
        <select
          aria-label={`${role ?? "orchestrator"} effort`}
          value={target.effort}
          onChange={(event) => updateTarget(role, { effort: event.target.value })}
          className={selectClass}
        >
          <option value="">adapter default</option>
          {efforts.map((effort) => (
            <option key={effort} value={effort}>
              {effort}
            </option>
          ))}
          {staleOption(target.effort, efforts.includes(target.effort))}
        </select>
      </div>
    );
  };

  return (
    <section className="rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] p-5">
      <SectionHeader
        title="Agent Supervision"
        desc="Controls supervised formula work: choose an adapter, model, and effort per role, or let adaptive mode route eligible work. Disabled keeps dispatch behavior unchanged. Default: OFF."
      />
      <div className="divide-y divide-[var(--cos-border)]">
        <FieldRow label="Enable supervision">
          <Toggle
            checked={routing.enabled}
            onChange={(v) => onChange({ ...routing, enabled: v })}
            label={routing.enabled ? "Enabled" : "Disabled"}
          />
        </FieldRow>
        {routing.enabled && (
          <>
            <FieldRow label="Trigger mode">
              <select
                value={routing.mode}
                onChange={(e) =>
                  onChange({ ...routing, mode: e.target.value as ModelRouting["mode"] })
                }
                className={selectClass}
              >
                <option value="explicit">Explicit</option>
                <option value="suggest">Suggest</option>
                <option value="adaptive">Adaptive</option>
              </select>
              <select
                value={routing.complexity_threshold}
                onChange={(e) =>
                  onChange({
                    ...routing,
                    complexity_threshold: e.target.value as ModelRouting["complexity_threshold"],
                  })
                }
                disabled={routing.mode !== "adaptive"}
                className={selectClass}
              >
                {["CLEAR", "COMPLICATED", "COMPLEX", "CHAOTIC"].map((level) => (
                  <option key={level}>{level}</option>
                ))}
              </select>
            </FieldRow>
            <FieldRow label="Fallback">
              <select
                value={routing.fallback_policy}
                onChange={(e) =>
                  onChange({
                    ...routing,
                    fallback_policy: e.target.value as ModelRouting["fallback_policy"],
                  })
                }
                className={selectClass}
              >
                <option value="fail_closed">Fail closed</option>
                <option value="same_adapter_default">Same adapter default</option>
                <option value="next_eligible">Next eligible adapter</option>
              </select>
            </FieldRow>
            <FieldRow label="Parallel limit">
              <NumInput
                value={routing.max_parallel}
                min={1}
                max={16}
                onChange={(value) => onChange({ ...routing, max_parallel: value })}
              />
            </FieldRow>
            <FieldRow label="Capacity cooldown">
              <NumInput
                value={routing.cooldown.default_seconds}
                min={1}
                max={86400}
                onChange={(value) =>
                  onChange({
                    ...routing,
                    cooldown: { ...routing.cooldown, default_seconds: value },
                  })
                }
              />
              <span className="text-xs text-[var(--cos-muted)]">to</span>
              <NumInput
                value={routing.cooldown.maximum_seconds}
                min={1}
                max={604800}
                onChange={(value) =>
                  onChange({
                    ...routing,
                    cooldown: { ...routing.cooldown, maximum_seconds: value },
                  })
                }
              />
              <span className="text-xs text-[var(--cos-muted)]">seconds</span>
            </FieldRow>
            <FieldRow label="Orchestrator">
              {targetControls(null, routing.orchestrator)}
              {availableAdapters.length === 0 && (
                <span className="text-[10px] text-[var(--cos-warn)]">
                  no dispatch-ready adapter installed
                </span>
              )}
            </FieldRow>
            {(roleData?.roles ?? []).map((role) => (
              <FieldRow key={role} label={role}>
                {targetControls(
                  role,
                  routing.roles[role] ?? { adapter: "", model: "", effort: "" },
                )}
              </FieldRow>
            ))}
          </>
        )}
      </div>
      <p className="mt-3 text-[10px] leading-relaxed text-[var(--cos-muted)]">
        Adapters, models, efforts, and dispatch capabilities come from each adapter descriptor.
        Capacity failures pause only the affected adapter and recovery is probed automatically.
      </p>
    </section>
  );
}
