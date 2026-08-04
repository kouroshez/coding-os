---
id: TASK-882
title: "Ship opt-in configurable agent supervision"
swimlane: core
kind: feature
epic: null
labels: [orchestration, adapters, model-routing, hub, docs-update, ready]
status: icebox
priority: P1
appetite: 3d
created: 2026-08-04
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-882: Ship opt-in configurable agent supervision

**Outcome (one sentence):** Users can opt into a manifest-discovered supervision feature, choose installed runtimes and per-role model policies, and keep the system completely inert when disabled or when only one runtime is installed.

## Read First
- docs/architecture/raptor-consolidation.md
- docs/governance/vision.md
- docs/engineering/agent-hub-orchestration.md
- docs/engineering/hub-architecture.md
- docs/engineering/config-composition.md
- docs/adapters/claude-sdk.md
- docs/adapters/codex.md
- src/core/schemas/adapter.schema.json
- src/core/web/routes/cognition.py
- src/core/thinking_os/dispatcher.py

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** the feature is disabled
  **When** prompts, formula runs, Hub chats, hooks, and CLI sessions execute
  **Then** current single-runtime behavior is unchanged and no supervision tokens, processes, persistence, or UI controls are activated.
- **Given** one or more installed adapters advertise interactive runtime capabilities
  **When** the user enables supervision
  **Then** all adapter/model/effort choices are discovered from manifests and editable as per-role policies without provider or model literals in core.
- **Given** a user selects one adapter with several models
  **When** a supervised workflow runs
  **Then** roles can be routed among those models without requiring another adapter.
- **Given** several compatible adapters
  **When** a workflow fans out, retries, resumes, cancels, or requests permission
  **Then** stable run identity, capability negotiation, checkpoints, budgets, cancellation propagation, writer leases, and typed evidence outputs remain deterministic and observable.
- **Given** an adapter or capability is missing, stale, unauthenticated, or fails mid-run
  **When** policy resolution occurs
  **Then** the system follows the configured fallback/fail policy and never invents parity or silently replays an uncertain write.
- **Given** the feature is shipped
  **When** the current repository tree, UI copy, public metadata, application logs, and newly created commit metadata are inspected
  **Then** implementation language stays product-native and contains no benchmark-project names or research-document title/path.

## Work Log
- 2026-08-04 [019fc9ac-216e-7211-a224-]: Research and architecture pass complete. Raptor review favors one capability-driven adapter registry, the existing…
