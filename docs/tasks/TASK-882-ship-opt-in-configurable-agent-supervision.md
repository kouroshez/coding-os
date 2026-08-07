---
id: TASK-882
title: "Ship opt-in configurable agent supervision"
swimlane: core
kind: feature
epic: null
labels: [orchestration, adapters, model-routing, hub, docs-update, ready]
status: complete
priority: P1
appetite: 3d
created: 2026-08-04
started: 2026-08-06
completed: 2026-08-07
agent_session: ses-claude-20260806-204356-2f94
depends_on: []
blocked_by: []
references: []
---
# TASK-882: Ship opt-in configurable agent supervision

**Outcome (one sentence):** Users can opt into manifest-discovered supervision, route roles across any installed runtime or model, and keep unhealthy or rate-limited capacity out of selection until it safely recovers.

## Read First
- docs/architecture/raptor-consolidation.md
- docs/governance/vision.md
- docs/engineering/agent-supervision.md
- docs/engineering/hub-architecture.md
- docs/engineering/config-composition.md
- docs/adapters/claude-sdk.md
- docs/adapters/codex.md
- src/core/schemas/adapter.schema.json
- src/core/web/routes/cognition.py
- src/core/thinking_os/dispatcher.py

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** supervision is disabled
  **When** prompts, formula runs, Hub chats, hooks, and CLI sessions execute
  **Then** current single-runtime behavior is unchanged and no supervision tokens, processes, health persistence, or UI controls are activated.
- **Given** one or more configured adapters advertise dispatch capabilities
  **When** the user enables supervision
  **Then** adapter, model, and effort choices are discovered from manifests and editable as per-role policies without provider or model literals in core.
- **Given** one adapter exposes several models
  **When** a supervised workflow runs
  **Then** roles can be routed among those models without requiring another adapter.
- **Given** several eligible adapters
  **When** a workflow fans out
  **Then** each role resolves and invokes its own adapter, model, and effort policy while the parent receives deterministic typed evidence.
- **Given** an adapter reports a retryable capacity or rate-limit failure
  **When** more work is routed before its retry window
  **Then** the adapter is excluded without repeated paid probes, its cooldown and reason are observable, and configured fallback policy is applied.
- **Given** an adapter cooldown expires
  **When** new work becomes eligible
  **Then** the adapter enters a bounded half-open probe, returns to healthy after success, and extends cooldown without a retry storm after another capacity failure.
- **Given** future adapters add manifest-compatible runtime entrypoints and normalized failure metadata
  **When** they are installed
  **Then** supervision discovers and routes them without editing provider literals in core.
- **Given** an adapter is missing, unauthenticated, incompatible, or fails with an uncertain write
  **When** policy resolution occurs
  **Then** the configured fail or fallback behavior is followed without invented parity, unsafe replay, or silent adapter switching.
- **Given** implementation verification passes
  **When** the release workflow runs
  **Then** the next version is published from the verified commit to GitHub and PyPI with matching version and artifact evidence.
- **Given** the feature is shipped
  **When** the current tree, UI copy, public metadata, application logs, and newly created commit metadata are inspected
  **Then** implementation language remains product-native and contains no external benchmark names or obsolete research-document title/path.

## Work Log
- 2026-08-04 [019fc9ac-216e-7211-a224-]: Research and architecture pass complete. Raptor review favors one capability-driven adapter registry, the existing…
- 2026-08-07 [019fc9ac-216e-7211-a224-]: Docs-first contract now defines one manifest-driven registry, one persistent capacity circuit, default-off policy,…
- 2026-08-07 [codex]: Implemented opt-in provider-neutral supervision: descriptor discovery, per-role adapter/model/effort policy, mixed…
- 2026-08-07 [codex]: Implemented opt-in adapter-neutral formula supervision with manifest discovery, per-role adapter/model/effort policy,…
- 2026-08-07 [codex]: GitHub CI exposed generated OpenAPI snapshot drift for the new adapter-health route. Regenerated…
- 2026-08-07 [codex]: Regenerated all 8 golden sections after hook/rule changes. Full modularity gate now passes: referential/render/toggle…
- 2026-08-07 [codex]: Added one kernel-owned supervision policy service shared by Hub, CLI, and MCP; introduced cos supervision and…
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit supervision.py
- 2026-08-07 [claude]: Edit adapter_registry.py
- 2026-08-07 [claude]: Edit adapter_registry.py
- 2026-08-07 [claude]: Edit adapter_registry.py
- 2026-08-07 [claude]: Edit cognition.py
- 2026-08-07 [claude]: Edit cognition.py
- 2026-08-07 [claude]: Edit cognition.py
- 2026-08-07 [claude]: Edit config.py
- 2026-08-07 [claude]: Edit supervision_commands.py
- 2026-08-07 [claude]: Edit claude-sdk.md
- 2026-08-07 [claude]: Edit claude-sdk.md
- 2026-08-07 [claude]: Edit adapter_registry.py
- 2026-08-07 [claude]: commit aeaf4f148e — fix(supervision): restore adapter validation and protect the capacity recovery probe
- 2026-08-07 [claude]: commit e76e67f75e — chore(board): record the supervision code-review fixes on TASK-882
- 2026-08-07 [claude]: Edit agent-supervision.md
- 2026-08-07 [claude]: Edit agent-supervision.md
- 2026-08-07 [claude]: Edit agent-supervision.md
- 2026-08-07 [claude]: Edit agent-supervision.md
- 2026-08-07 [claude]: Edit agent-supervision.md
- 2026-08-07 [claude]: Edit agent-supervision.md
- 2026-08-07 [claude]: Edit README.md
- 2026-08-07 [claude]: Edit agent-supervision-setup.md
- 2026-08-07 [claude]: Edit supervision.py
- 2026-08-07 [claude]: Edit supervision.py
- 2026-08-07 [claude]: Edit supervision.py
- 2026-08-07 [claude]: Edit supervision.py
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit cognition.py
- 2026-08-07 [claude]: Edit adapter_registry.py
- 2026-08-07 [claude]: Edit settings.py
- 2026-08-07 [claude]: Edit settings.py
- 2026-08-07 [claude]: Edit SettingsPage.tsx
- 2026-08-07 [claude]: Edit SettingsPage.tsx
- 2026-08-07 [claude]: Edit adapter.schema.json
- 2026-08-07 [claude]: Edit supervision.py
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit cognition.py
- 2026-08-07 [claude]: Edit agent-supervision.md
- 2026-08-07 [claude]: Edit agent-supervision-setup.md
- 2026-08-07 [claude]: Edit agent-supervision-setup.md
- 2026-08-07 [claude]: Edit test_supervision.py
- 2026-08-07 [claude]: Edit test_supervision.py
- 2026-08-07 [claude]: Edit test_supervision.py
- 2026-08-07 [claude]: Edit test_supervision.py
- 2026-08-07 [claude]: Edit cognition.py
- 2026-08-07 [claude]: Edit test_cli.py
- 2026-08-07 [claude]: Edit test_cli.py
- 2026-08-07 [claude]: Edit claude-sdk.md
- 2026-08-07 [claude]: Edit claude-sdk.md
- 2026-08-07 [claude]: Edit dispatcher-contract.md
- 2026-08-07 [claude]: Edit test_cognition_tools.py
- 2026-08-07 [claude]: Closed the review gaps: trigger modes now enforced via one predicate (supervision.policy_applies) read by both the…
- 2026-08-07 [claude]: Edit supervision.py
- 2026-08-07 [claude]: Edit supervision.py
- 2026-08-07 [claude]: Edit supervision.py
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit test_adapter_capacity_errors.py
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit test_supervision.py
- 2026-08-07 [claude]: Edit test_supervision.py
- 2026-08-07 [claude]: Edit agent-supervision.md
- 2026-08-07 [claude]: Edit agent-supervision.md
- 2026-08-07 [claude]: Edit agent-supervision-setup.md
- 2026-08-07 [claude]: Edit agent-supervision-setup.md
- 2026-08-07 [claude]: Edit agent-supervision-setup.md
- 2026-08-07 [claude]: commit 21c608bb5c — fix(supervision): hold the recovery probe for its whole run and report the soonest recovery
- 2026-08-07 [claude]: commit fc6f852ead — test(adapters): require every dispatch adapter to normalize provider limits
- 2026-08-07 [claude]: commit ab68c36e02 — docs(supervision): document probe-lease duration, fleet exhaustion, and the adapter contract
- 2026-08-07 [claude]: Simulated a two-adapter fleet hitting provider limits and found three real defects the unit tests missed: the 30s…
- 2026-08-07 [claude]: commit 443631f31a — chore(board): log the multi-adapter capacity findings on TASK-882
- 2026-08-07 [claude]: Edit test_lease_leak.py
- 2026-08-07 [claude]: Edit test_half_open_stick.py
- 2026-08-07 [claude]: Edit test_empty_param.py
- 2026-08-07 [claude]: Edit sdk_dispatcher.py
- 2026-08-07 [claude]: Edit sdk_dispatcher.py
- 2026-08-07 [claude]: Edit adapter.yaml
- 2026-08-07 [claude]: Edit adapter.schema.json
- 2026-08-07 [claude]: Edit supervision.py
- 2026-08-07 [claude]: Edit supervision.py
- 2026-08-07 [claude]: Edit supervision.py
- 2026-08-07 [claude]: Edit supervision.py
- 2026-08-07 [claude]: Edit supervision.py
- 2026-08-07 [claude]: Edit supervision.py
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit dispatcher.py
- 2026-08-07 [claude]: Edit config.py
- 2026-08-07 [claude]: Edit test_supervision.py
- 2026-08-07 [claude]: Edit test_supervision.py
- 2026-08-07 [claude]: Edit test_supervision.py
- 2026-08-07 [claude]: Edit test_adapter_capacity_errors.py
- 2026-08-07 [claude]: Edit test_adapter_capacity_errors.py
- 2026-08-07 [claude]: Edit agent-supervision.md
- 2026-08-07 [claude]: Edit agent-supervision.md
- 2026-08-07 [claude]: Edit agent-supervision.md
- 2026-08-07 [claude]: Edit agent-supervision-setup.md
- 2026-08-07 [claude]: Edit agent-supervision-setup.md
- 2026-08-07 [claude]: Edit pool_sim.py
- 2026-08-07 [claude]: commit ecce06695f — fix(supervision): meter capacity per model pool instead of per adapter
- 2026-08-07 [claude]: commit 312334b772 — test(supervision): cover pool isolation, probe-lease leaks, and stale cooling state
- 2026-08-07 [claude]: commit e745bf128e — docs(supervision): record what a provider limit actually applies to
- 2026-08-07 [claude]: Researched the provider's own rate-limit spec and found the model was wrong at the root: limits are metered per…
- 2026-08-07 [claude]: commit cc202aab9c — chore(board): log the pool-scoping research and fixes on TASK-882
- 2026-08-07 [claude]: commit a4b5c4e502 — chore(board): record the closing work-log entry on TASK-882
- 2026-08-07 [claude]: Edit SettingsPage.tsx
- 2026-08-07 [claude]: Edit SettingsPage.test.tsx
- 2026-08-07 [claude]: commit 5147541bb6 — fix(hub): stop the settings toggle reading inverted
- 2026-08-07 [claude]: commit 7b13fd6d85 — chore(board): log the graph cleanup and toggle fix on TASK-882
- 2026-08-07 [claude]: Edit transition_gates_cli.py
- 2026-08-07 [claude]: Edit transition_gates_cli.py
- 2026-08-07 [claude]: Edit transition_gates_cli.py
- 2026-08-07 [claude]: Edit transition_gates_cli.py
- 2026-08-07 [claude]: Edit update.py
- 2026-08-07 [claude]: Edit test_cli.py
- 2026-08-07 [claude]: commit 7bb6cc4438 — fix(board): anchor the DoD verify ledger to the project root
- 2026-08-07 [claude]: Status transitioned to complete via cos task-done.
