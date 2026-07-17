---
id: TASK-841
title: "Close the \"0 trusted\" learning loop on the MCP completion path + unify .learn-suggestions"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-07-17
started: 2026-07-17
completed: 2026-07-17
agent_session: ses-claude-20260717-014556-89d0
depends_on: []
blocked_by: []
references: []
---
# TASK-841: Close the "0 trusted" learning loop on the MCP completion path + unify .learn-suggestions

**Outcome (one sentence):** Surfaced learned patterns get validated on EVERY task completion (MCP cos_task_move to=complete, not only CLI task-done), so times_validated rises and patterns can reach the Trusted tier. .learn-suggestions has one writer contract (panel-dir), and the session-scoped agent_metrics row carries a real outcome, not a hardcoded 'success'.

## Read First
- docs/engineering/learning-extraction.md
- src/core/hooks/_helpers/auto_validate_lessons.py
- src/core/board_os/mcp_tools.py
- src/core/thinking_os/server.py
- src/core/thinking_os/session_enrich.py

## Repro Steps
Complete a task via the MCP cos_task_move(to='complete') tool (not the CLI). remind-learn-validate.sh is a PostToolUse Bash hook, so it never fires — no learn_validate call, pattern_validations stays empty, times_validated stays 0, and cos_learn_suggest patterns never reach Trusted (needs times_validated>=3). Separately: cos_learn_suggest (MCP) appends to $COS_AGENT_DIR/.learn-suggestions while auto_compose + the reminder + session reset all use $COS_PANEL_DIR — the MCP suggestions are written where nothing reads them. And session_enrich writes agent_metrics.outcome='success' unconditionally, inflating success_rate/time_to_solution trends.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a task whose Orient surfaced patterns (panel .learn-suggestions populated) **When** it is completed via the MCP cos_task_move(to='complete') tool **Then** each surfaced pattern gets a pattern_validations row and times_validated increments (loop closes without the Bash hook).
**Given** cos_learn_suggest is called via MCP **When** it persists the surfaced ids **Then** they land in the panel-dir .learn-suggestions (the same file auto_compose writes, the reminder reads, and session-context resets) — not an unpruned agent-dir append.
**Given** a session that recorded a backtrack_event **When** session_enrich writes its agent_metrics row **Then** outcome is 'rework', not the hardcoded 'success'.

## Work Log
- 2026-07-17 [claude]: Edit learning-extraction.md
- 2026-07-17 [claude]: Edit learning-extraction.md
- 2026-07-17 [claude]: Plan: extract one shared primitive tools.learning.validate_surfaced_lessons(conn, session_id, suggestions_path)…
- 2026-07-17 [claude]: Edit learning.py
- 2026-07-17 [claude]: Edit learning.py
- 2026-07-17 [claude]: Edit auto_validate_lessons.py
- 2026-07-17 [claude]: Edit mcp_tools.py
- 2026-07-17 [claude]: Edit mcp_tools.py
- 2026-07-17 [claude]: Edit server.py
- 2026-07-17 [claude]: Edit session_enrich.py
- 2026-07-17 [claude]: Edit verify_cluster_b.py
- 2026-07-17 [claude]: Edit verify_cluster_b.py
- 2026-07-17 [claude]: Edit verify_cluster_b.py
- 2026-07-17 [claude]: Edit verify_cluster_b.py
- 2026-07-17 [claude]: Edit test_mcp_tools.py
- 2026-07-17 [claude]: Edit test_session.py
- 2026-07-17 [claude]: Verified: e2e driver (all 3 fixes, real DB + real session_enrich.py subprocess → outcome=rework); board_os suite 527…
- 2026-07-17 [claude]: committed 94b1bd4a · 2 files
