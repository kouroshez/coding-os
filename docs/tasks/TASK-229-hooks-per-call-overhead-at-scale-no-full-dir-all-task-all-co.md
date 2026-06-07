---
id: TASK-229
title: "Hooks per-call overhead at scale: no full-dir/all-task/all-commit scan on every tool call"
swimlane: core
kind: feature
epic: enterprise-scale
labels: [scale, hooks, performance, ready]
status: icebox
priority: P2
appetite: 2d
created: 2026-06-07
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-229: Hooks per-call overhead at scale: no full-dir/all-task/all-commit scan on every tool call

**Outcome (one sentence):** No PreToolUse/PostToolUse hook does an O(all-tasks)/O(all-commits)/full-tree scan on every agent tool call (which at 100K tasks adds seconds of latency per edit): audit every registered hook for ls docs/tasks/*, git log, rglob, or full-table DB reads on the hot path and replace with cached/indexed/debounced lookups. Verified by per-tool-call hook latency staying flat as task count grows. See audit-enterprise-scale-2026-06-07.md (hooks findings).

## Read First
- docs/tasks/audits/audit-enterprise-scale-2026-06-07.md
- src/core/hooks/registry.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** PreToolUse/PostToolUse hooks fire on every agent tool call and some scan all tasks/commits/files.
- **When** a hook runs on a single Edit/Bash at 100K-task / 1M-commit scale.
- **Then** no registered hook performs an O(all-tasks)/O(all-commits)/full-tree scan on the hot path (each audited + replaced with cached/indexed/debounced lookups), and measured per-tool-call hook latency stays flat as task count grows.

## Work Log
