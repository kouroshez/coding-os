---
id: TASK-859
title: "Close lifecycle drift: bilingual mode classifier, unadvertised bypass, icebox-zombie detection"
swimlane: "board_os"
kind: bug
epic: null
labels: [lifecycle, drift, governance, hooks, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-02
started: 2026-08-02
completed: 2026-08-02
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-859: Close lifecycle drift: bilingual mode classifier, unadvertised bypass, icebox-zombie detection

**Outcome (one sentence):** Work can no longer silently bypass the board: Persian implementation prompts engage task enforcement, the manual .task-current bypass is no longer advertised, and icebox cards carrying completion evidence surface as zombies in reconcile + board.

## Read First
- src/core/hooks/classify-task-mode.sh
- src/core/hooks/enforce-task-start.sh
- src/core/board_os/mcp_tools.py
- docs/governance/task-lifecycle.md
- src/core/hooks/warn-abandoned-task.sh

## Repro Steps
TASK-843: created directly in icebox with work-log "Implemented + verified" + ready label → invisible to warn-abandoned-task (ready exempt), invisible to cos_task_reconcile (scans in_progress/testing only). TASK-830: post-commit hook attributed unrelated commit e0dc8f82 to a never-started icebox card. Root enabler: classify-task-mode.sh claims bilingual but IMPL_RE/QUERY_RE/EXPLORE_RE are English-only, so Persian sessions run adhoc → enforce-task-start exits early.

## Acceptance (G/W/T) — *this IS the Definition of Done*
1. **Given** a Persian implementation prompt ( / ), **When** classify-task-mode.sh classifies it, **Then** .task-mode is propose-formal — not adhoc or chore.
2. **Given** an icebox card whose work log carries "committed <sha>" or an implementation claim (TASK-843 shape), **When** cos_task_reconcile runs, **Then** the card is listed with classification zombie_icebox and an actionable recommendation.
3. **Given** the same card, **When** cos_task_board renders it, **Then** the card is flagged stale with a zombie-specific reason.
4. **Given** enforce-task-start blocks a code edit, **When** the remediation message prints, **Then** it offers only task-create/task-start and the trivial-gate path — no manual .task-current write-state line.

## Work Log
- 2026-08-02 [claude]: Deliberation: fix the four existing drift surfaces in place (verb regex, remediation text, reconcile scan, lifecycle…
- 2026-08-02 [claude]: Edit task-lifecycle.md
- 2026-08-02 [claude]: Edit task-lifecycle.md
- 2026-08-02 [claude]: Edit classify-task-mode.sh
- 2026-08-02 [claude]: Edit enforce-task-start.sh
- 2026-08-02 [claude]: Edit classify-task-mode.sh
- 2026-08-02 [claude]: Edit enforce-task-start.sh
- 2026-08-02 [claude]: Edit mcp_tools.py
- 2026-08-02 [claude]: Edit mcp_tools.py
- 2026-08-02 [claude]: Edit mcp_tools.py
- 2026-08-02 [claude]: Edit mcp_tools.py
- 2026-08-02 [claude]: Edit mcp_tools.py
- 2026-08-02 [claude]: Edit test_mcp_tools.py
- 2026-08-02 [claude]: commit 10634d2dff — fix(board): flag icebox zombie cards + bilingual task-mode classifier
- 2026-08-02 [claude]: Edit zombie_check.py
- 2026-08-02 [claude]: Edit board.py
- 2026-08-02 [claude]: Edit board.py
- 2026-08-02 [claude]: Edit test_board_routes_attribution.py
- 2026-08-02 [claude]: Edit test_board_routes_attribution.py
- 2026-08-02 [claude]: Edit test_board_routes_attribution.py
- 2026-08-02 [claude]: Edit repos_debug.py
- 2026-08-02 [claude]: Edit test_board_routes_attribution.py
- 2026-08-02 [claude]: commit 8c70fb1dde — fix(web): attribute unowned panel move/reposition to the human actor
- 2026-08-02 [claude]: Fixed 4 drift surfaces + a 4th caught live: hub move/reposition stamped human drags with the active agent session…
