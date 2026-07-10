---
id: TASK-808
title: "Audit current OpenAI SDK and close Codex adapter capability gaps"
swimlane: adapters
kind: feature
epic: null
labels: [codex, adapter, openai-sdk, parity, research, ready]
status: in_progress
priority: P1
appetite: 3d
created: 2026-07-10
started: 2026-07-10
completed: null
agent_session: codex-20260710-adapter-audit
depends_on: []
blocked_by: []
references: []
---
# TASK-808: Audit current OpenAI SDK and close Codex adapter capability gaps

**Outcome (one sentence):** The Codex adapter has a current, evidence-backed capability contract, compatible OpenAI tooling versions, and tested implementations for every feasible gap without pretending Claude-only runtime hooks exist.

## Read First
- docs/adapters/codex.md
- docs/adapters/claude-sdk.md
- docs/engineering/dispatcher-contract.md
- src/adapters/codex/adapter.yaml
- src/adapters/claude/adapter.yaml

## Acceptance (G/W/T) - *this IS the Definition of Done*
- **Given** the repository dependency declarations
- **When** they are compared with current official OpenAI releases
- **Then** every active OpenAI SDK/CLI dependency is either upgraded compatibly or explicitly justified.

- **Given** current Codex and Claude runtime capabilities
- **When** the adapter contract is reviewed
- **Then** supported, emulated, degraded, and impossible capabilities are documented with official evidence.

- **Given** the documented feasible gaps
- **When** adapter and parity suites plus executable smoke checks run
- **Then** they pass and no derived artifact is hand-edited.

## Work Log
- 2026-07-10 [codex]: Baseline audit: CLI 0.144.1 equals npm stable; TS SDK 0.144.1 wraps CLI; Python SDK latest is 0.1.0b3 beta and pins…
