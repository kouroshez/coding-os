---
id: TASK-1116
title: "feat(hub): the model list comes from the runtime, so new models such as Fable 5.2 appear without a code change"
swimlane: adapters
kind: feature
epic: null
labels: [supervision, ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-11-24
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1116: feat(hub): the model list comes from the runtime, so new models such as Fable 5.2 appear without a code change

**Outcome (one sentence):** The Hub pickers and dispatch validation use the model catalog the runtime reports, cached per adapter and refreshed on cos update and Hub start, with adapter.yaml models kept only as the offline fallback, so a model Claude Code ships (Fable 5.2 today) is selectable after the next update with no code change.

## Read First
- docs/engineering/agent-supervision.md
- src/adapters/claude/adapter.yaml
- src/adapters/codex/adapter.yaml
- src/core/thinking_os/adapter_registry.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** Claude Code 2.1.331, **When** the catalog refreshes, **Then** it lists claude-fable-5-2 with its effort levels, taken from ClaudeSDKClient.get_server_info()['models'] (verified live on 2026-11-24).
- **Given** a cached runtime catalog, **When** the Hub renders a model picker or dispatch validates a model, **Then** both read the cached catalog, and adapter.yaml models only when no cache exists.
- **Given** the runtime cannot be started (offline, no auth), **When** the refresh runs, **Then** the previous cache or adapter.yaml is kept and the failure is logged, never an empty list.
- **Given** the Codex runtime, **When** the refresh runs, **Then** it uses Codex's own model listing if one exists, else keeps adapter.yaml, and the task records which.
- **Given** cos update, **When** it finishes, **Then** the catalog is refreshed in the same run.

## Work Log
