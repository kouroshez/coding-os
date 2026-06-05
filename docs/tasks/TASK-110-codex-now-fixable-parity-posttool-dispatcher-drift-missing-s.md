---
id: TASK-110
title: "Codex now-fixable parity — posttool dispatcher drift, missing Stop guardian, generate delegates from adapter.yaml"
swimlane: infra
kind: bug
epic: hook-remediation
labels: [codex, adapter, hooks, parity, audit-n6]
status: icebox
priority: P1
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-110: Codex now-fixable parity — posttool dispatcher drift, missing Stop guardian, generate delegates from adapter.yaml

**Outcome (one sentence):** codex-posttool-dispatch.sh runs all declared delegates (adds auto-reindex-shell-ops + auto-prune-deleted-files); Stop dispatcher gains verify-completion-claim + prevent-premature-done; dispatcher for-loops generated from adapter.yaml::delegates (or a parity test asserts set-equality).

## Read First
- src/adapters/codex/hooks/codex-posttool-dispatch.sh
- src/adapters/codex/adapter.yaml
- src/cli/hook_renderer.py

## Repro Steps
1. (fill in: exact steps to reproduce)
2. ...
Expected: ...
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
