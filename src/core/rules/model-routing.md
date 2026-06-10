# Model Routing — Auto Mode (settings-gated)

> **Rule:** When `model_routing.enabled` is on in `$COS_STATE_DIR/hub-settings.json`, the agent consults the kernel router before heavy work: call `cos_route_model` with the recorded gate complexity during Classify, and honor the result at every formula dispatch (`cos_dispatch_formula_run` / `cos_dispatch_parallel_run` accept `model` + `complexity`). When the toggle is off, this rule is inert — zero behavioral or token-cost difference.

## Why

The hub chat panel gets an "Auto" model option (settings-gated) that routes
each session server-side. CLI / VSCode-plugin sessions have no panel UI, so
parity comes from this rule + the `nudge-model-routing` UserPromptSubmit hook:
the hook injects a one-line directive (once per session, only while the toggle
is on) and this rule carries the full contract every adapter inherits via
`cos update`.

## The contract

1. **Toggle off (default)** — nothing fires. The hook exits before any
   output; no context is injected; dispatch behaviour is unchanged.
2. **Toggle on** — at Classify time, after `cos_classify_prompt` records the
   gate, call `cos_route_model(complexity=<gate>, domain=<routed domain>)`.
   Honor the recommendation when it is backed by history
   (`data_points > 0`); otherwise prefer the settings' `orchestrator_model`,
   else the adapter default.
3. **Dispatch** — pass the chosen model and the gate complexity to the run
   tools; the kernel precedence (claude-sdk.md §7.3) handles the rest
   (explicit > preset hint > role pref > empirical > default).
4. **Trace** — the routing decision must be visible: the run tools log
   `dispatch model resolved … via <source>`; the chat path emits an SSE
   `routing` event.

## Settings source (SSOT)

`hub-settings.json::model_routing` — written by the hub Settings page
(`/api/settings`), readable by every consumer fresh per call (no restart).
Models come from `src/adapters/*/adapter.yaml::models` (Rule 11 — no model
id literal in code or in this rule).

## See also

- [docs/engineering/hub-architecture.md § Hub settings contract](../../docs/engineering/hub-architecture.md)
- [docs/adapters/claude-sdk.md §7.3](../../docs/adapters/claude-sdk.md) — dispatch model precedence
- [src/core/hooks/nudge-model-routing.sh](../hooks/nudge-model-routing.sh) — the per-session directive injector
