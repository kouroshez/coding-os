---
id: TASK-1139
title: "fix(adapters): Codex trust and MCP check in doctor, memory seeded in consumers, prime-memory marker after emit"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-11-26
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1139: fix(adapters): Codex trust and MCP check in doctor, memory seeded in consumers, prime-memory marker after emit

**Outcome (one sentence):** Findings C3, C4, M1, M2 and L4 of docs/engineering/harness-loading-audit-2026-11.md are closed.

## Read First
- docs/engineering/harness-loading-audit-2026-11.md

## Repro Steps
`codex mcp list` in coding-os shows no coding-os server, and a fresh scaffold has no .agents/memory (audit C3, M1).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a fresh scaffold, **When** it is listed, **Then** .agents/memory/MEMORY.md exists and `cos memory-lint` passes.
- **Given** an untrusted Codex project, **When** `cos doctor` runs, **Then** it reports that Codex ignores the project config and MCP, with the one step to fix it.
- **Given** prime-memory-codex with a failing python, **When** the next prompt arrives, **Then** it retries the index.

## Work Log
