---
id: TASK-463
title: "Wire blocked outcome emit path (de-degenerate the flywheel signal)"
swimlane: "thinking_os"
kind: feature
epic: audit-remediation-2026-06
labels: [audit-remediation, flywheel, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-20
started: 2026-06-19
completed: 2026-06-19
agent_session: ses-claude-20260619-211916-fd8f
depends_on: []
blocked_by: []
references: []
---
# TASK-463: Wire blocked outcome emit path (de-degenerate the flywheel signal)

**Outcome (one sentence):** record_outcome derives a real 'blocked' outcome from task_status_history (parallel to _derive_rework) so partial/blocked are no longer structurally impossible; documents that 'partial' is explicit-only (no derivable signal) and that variance ultimately needs diverse consumer work (group F), not more heuristics.

## Read First
- src/core/thinking_os/record_outcome.py
- src/core/board_os/config.py
- src/cli/board_commands.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a task whose status history shows it entered 'blocked' before completing, **When** record_outcome runs at task-done, **Then** the recorded outcome is 'blocked' (not a hardcoded 'success').
**Given** a task that completed cleanly with no blocked/rework history, **When** record_outcome runs, **Then** the outcome stays 'success'.
**Given** the thinking_os test suite, **When** run, **Then** green including a new test asserting the blocked-derivation precedence (blocked > rework > success).

## Work Log
- 2026-06-20 [claude]: Edit record_outcome.py
- 2026-06-20 [claude]: Edit record_outcome.py
- 2026-06-20 [claude]: Edit test_record_outcome.py
- 2026-06-20 [claude]: Edit test_record_outcome.py
- 2026-06-20 [claude]: Edit learning-extraction.md
- 2026-06-20 [claude]: commit 52585aeb93 — feat(thinking_os): derive 'blocked' outcome from status history (flywheel emit path)
- 2026-06-20 [claude]: Status transitioned to complete via cos task-done.
- 2026-06-20 [claude]: Added _derive_blocked (status-history→blocked, precedence blocked>rework>success); partial stays explicit-only. 16…
