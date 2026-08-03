---
id: TASK-866
title: "Refresh Codex adapter against current official SDK"
swimlane: adapters
kind: feature
epic: null
labels: [codex, adapter, openai-sdk, parity, research, ready]
status: complete
priority: P1
appetite: 3d
created: 2026-08-03
started: 2026-08-03
completed: 2026-08-03
agent_session: ses-claude-20260803-182242-1f78
depends_on: []
blocked_by: []
references: []
---
# TASK-866: Refresh Codex adapter against current official SDK

**Outcome (one sentence):** The Codex adapter matches every current feasible coding-os runtime contract with documented unsupported boundaries and executable verification.

## Read First
- docs/adapters/codex.md
- docs/adapters/claude-sdk.md
- docs/engineering/dispatcher-contract.md
- docs/engineering/adapter-parity.md
- src/adapters/codex/adapter.yaml
- src/adapters/claude/adapter.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** current official Codex SDK documentation, installed runtime metadata, and repository dependency declarations
- **When** versions and supported interfaces are compared
- **Then** every active Codex SDK or CLI dependency is current or explicitly justified with evidence.

- **Given** the Claude adapter and coding-os dispatcher, hooks, installation, and capability contracts
- **When** they are compared against the Codex adapter
- **Then** a reviewed checklist classifies every capability as supported, emulated, degraded, impossible, or an actionable gap before code changes.

- **Given** the actionable Codex gaps
- **When** the smallest adapter-scoped implementation is completed
- **Then** targeted tests, adapter parity tests, generated-artifact checks, executable smoke tests, and final diff review pass.

## Work Log
- 2026-08-03 [claude]: Refreshed Codex adapter to openai-codex 0.144.4; added backend-aware SDK availability, pinned-runtime behavior,…
- 2026-08-03 [claude]: committed 2abec02a · 11 files
- 2026-08-03 [claude]: Status transitioned to complete via cos task-done.
