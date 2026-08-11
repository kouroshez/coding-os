// Shapes of .coding-os/hub-settings.json as served by routes/settings.py.
// claude_auth is the masked read shape (_masked_settings): mode +
// api_key_set + api_key_preview — the raw key never crosses the wire.

export interface BudgetCap {
  enabled: boolean;
  cap_usd: number;
}

export interface TraceRotation {
  gzip_age_days: number;
  delete_age_days: number;
}

export interface ModelRouting {
  enabled: boolean;
  orchestrator_model: string;
  mode: "explicit" | "suggest" | "adaptive";
  complexity_threshold: "CLEAR" | "COMPLICATED" | "COMPLEX" | "CHAOTIC";
  fallback_policy: "fail_closed" | "same_adapter_default" | "next_eligible";
  max_parallel: number;
  orchestrator: AdapterTarget;
  roles: Record<string, AdapterTarget>;
  cooldown: { default_seconds: number; maximum_seconds: number };
}

export interface AdapterTarget {
  adapter: string;
  model: string;
  effort: string;
}

const DEFAULT_ROUTING: ModelRouting = {
  enabled: false,
  orchestrator_model: "",
  mode: "explicit",
  complexity_threshold: "COMPLICATED",
  fallback_policy: "fail_closed",
  max_parallel: 3,
  orchestrator: { adapter: "", model: "", effort: "" },
  roles: {},
  cooldown: { default_seconds: 300, maximum_seconds: 3600 },
};

export type ModelRoutingPayload = Partial<
  Omit<ModelRouting, "orchestrator" | "roles" | "cooldown">
> & {
  orchestrator?: Partial<AdapterTarget>;
  roles?: Record<string, Partial<AdapterTarget>>;
  cooldown?: Partial<ModelRouting["cooldown"]>;
};

export function normalizeModelRouting(value?: ModelRoutingPayload | null): ModelRouting {
  return {
    ...DEFAULT_ROUTING,
    ...value,
    orchestrator: { ...DEFAULT_ROUTING.orchestrator, ...(value?.orchestrator ?? {}) },
    roles: Object.fromEntries(
      Object.entries(value?.roles ?? {}).map(([role, target]) => [
        role,
        { adapter: "", model: "", effort: "", ...target },
      ]),
    ),
    cooldown: { ...DEFAULT_ROUTING.cooldown, ...(value?.cooldown ?? {}) },
  };
}

export interface AutoSpawn {
  enabled: boolean;
}

// Masked shape returned by GET/PATCH — the raw key never crosses the wire
// after being stored (settings.py::_masked_settings).
export interface ClaudeAuth {
  mode: "subscription" | "api_key";
  api_key_set: boolean;
  api_key_preview: string;
}

export interface Settings {
  budget_cap: BudgetCap;
  trace_rotation: TraceRotation;
  model_routing: ModelRouting;
  auto_spawn: AutoSpawn;
  claude_auth: ClaudeAuth;
}

export interface SettingsPayload {
  settings: Settings;
  env_overrides: Record<string, string>;
}
