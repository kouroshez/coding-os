---
id: TASK-110
title: "Codex now-fixable parity — posttool dispatcher drift, missing Stop guardian, generate delegates from adapter.yaml"
swimlane: infra
kind: bug
epic: hook-remediation
labels: [codex, adapter, hooks, parity, audit-n6, ready]
status: complete
priority: P1
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-110: Codex now-fixable parity — posttool dispatcher drift, missing Stop guardian, generate delegates from adapter.yaml

**Outcome (one sentence):** The codex PostToolUse dispatcher fires `auto-reindex-shell-ops` + `auto-prune-deleted-files` (declared in adapter.yaml but unwired); a parity test asserts every codex dispatcher for-loop equals its adapter.yaml delegates so they can't drift; the Stop intent hooks stay Claude-only (refiled as TASK-153) because their effect is exit-0 stdout the dispatcher drops.

## Read First
- src/adapters/codex/hooks/codex-posttool-dispatch.sh
- src/adapters/codex/adapter.yaml
- tests/test_adapter_parity.py

## Repro Steps
1. On Codex, run a shell `mv`/`rm`: the graph goes stale and accrues zombie rows because `auto-reindex-shell-ops`/`auto-prune-deleted-files` are in adapter.yaml's PostToolUse delegates but missing from the dispatcher for-loop.
2. The dispatcher .sh and adapter.yaml are both hand-maintained with no test → silent drift.
Expected: the two side-effect hooks fire on Codex; a test catches dispatcher⇄yaml drift.
Actual: declared-but-unwired; no drift guard.

## Acceptance (G/W/T)
- **Given** the codex PostToolUse dispatcher, **When** it runs, **Then** its for-loop includes `auto-reindex-shell-ops.sh` + `auto-prune-deleted-files.sh` in adapter.yaml order.
- **Given** every codex `*-dispatch.sh`, **When** the parity test runs, **Then** the for-loop delegate set equals the adapter.yaml delegates for that dispatcher.
- **Given** verify-completion-claim/prevent-premature-done (exit-0-stdout hooks), **When** considered for the Stop dispatcher, **Then** they stay Claude-only (no silent no-op) and the stdout-forwarding enabler is tracked in TASK-153.

## Work Log
- 2026-06-05 [claude]: 6a wired auto-reindex-shell-ops+auto-prune-deleted-files in codex posttool dispatcher (side-effect hooks, stdout-drop ir
