---
id: TASK-114
title: "Fix enforce-anti-ambiguity dead gate — wire cos_ambiguity_check to write the cache marker + exit 2"
swimlane: core
kind: bug
epic: hook-remediation
labels: [hooks, cognition, audit-n10, ready]
status: archive
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
# TASK-114: Fix enforce-anti-ambiguity dead gate — wire cos_ambiguity_check to write the cache marker + exit 2

**Outcome (one sentence):** enforce-anti-ambiguity becomes real enforcement — reads the canonical ambiguity_violations DB table for the session and blocks (exit 2) on unresolved violations; cos_ambiguity_check clears prior rows each check so a pass clears the gate.

## Read First
- src/core/hooks/enforce-anti-ambiguity.sh
- src/core/thinking_os/tools/cognition.py

## Repro Steps
1. cos_ambiguity_check on a failing bundle records ambiguity_violations rows, but the hook read `.ambiguity-cache` which NO production code writes → it always hit `[[ ! -f cache ]] && exit 0` (zero enforcement).
2. Even with a cache, the FAIL branch used `exit 1` (generic error) not `exit 2` (tool-cancel) → would not block.
Expected: a recorded ambiguity violation blocks the next code Write/Edit.
Actual: the gate is dead.

## Acceptance (G/W/T)
- **Given** the session has unresolved rows in ambiguity_violations (from cos_ambiguity_check)
- **When** enforce-anti-ambiguity.sh runs on a non-CLEAR code Write/Edit
- **Then** it exits 2 listing the criteria; a subsequent passing check clears the session's rows so the gate reopens; fail-open when sqlite3/DB/session unresolvable; the clear-on-pass test passes.

## Work Log
