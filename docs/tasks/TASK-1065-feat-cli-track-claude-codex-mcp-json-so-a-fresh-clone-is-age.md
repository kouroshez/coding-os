---
id: TASK-1065
title: "feat(cli): track .claude/.codex/.mcp.json so a fresh clone is agent-ready"
swimlane: cli
kind: feature
epic: null
labels: [ready]
status: icebox
priority: P0
appetite: 1d
created: 2026-10-24
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1065: feat(cli): track .claude/.codex/.mcp.json so a fresh clone is agent-ready

**Outcome (one sentence):** A consumer project cloned on another machine, CI or a cloud session has working hooks, rules, skills and MCP config without running any setup: adapter dirs are committed and every link resolves inside the repo to a pinned, vendored copy of core.

## Read First
- docs/architecture/adr/0010-consumer-distribution-version-gate.md
- docs/engineering/state-files.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a project after `cos init`/`cos update` **When** `git ls-files .claude .codex .mcp.json` runs **Then** the adapter files are tracked
- **Given** that project cloned to a new path **When** every symlink under .claude/.codex is resolved **Then** none dangles and none points outside the clone
- **Given** coding-os core changes **When** the consumer has not run `cos update` **Then** its hooks still run the vendored version (no live propagation)
- **Given** `cos eject` **When** it runs **Then** vendored files and links are removed too

## Work Log
