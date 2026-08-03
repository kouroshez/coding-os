---
id: TASK-775
title: "Apply max-effort review findings: move $HOME DB guard to init_db, fix Work Log reorder via full-body board edit, memory content, dedup"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: archive
priority: P1
appetite: 1d
created: 2026-07-04
started: 2026-07-04
completed: 2026-07-04
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-775: Apply max-effort review findings: move $HOME DB guard to init_db, fix Work Log reorder via full-body board edit, memory content, dedup

**Outcome (one sentence):** The self-review's confirmed defects in this session's fixes are corrected: resolve_db_path no longer raises (so ImportError-only callers keep working) and the phantom-DB guard moves to init_db's mkdir chokepoint (which also closes the DEFAULT_DB_PATH bypass); the board drawer sends the full task body so the Work Log is preserved in place without producer re-append (no section reorder, no phantom edit) and the duplicated _extract_worklog_section is removed; memory_search only builds the content body when include_body is set.

## Read First
- src/core/thinking_os/database.py
- src/core/board_os/mcp_tools.py
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx
- src/core/thinking_os/tools/memory.py

## Repro Steps
Max-effort /code-review of commits ab35f7e5..f86404cb surfaced: database.py:167 RuntimeError escapes ImportError-only callers; database.py:127 DEFAULT_DB_PATH bypasses the guard; mcp_tools.py:3001 Work Log re-append reorders below Rollback + phantom edit; mcp_tools.py:2884 duplicates existing extractor; memory.py:429 content set-then-pop.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** resolve_db_path() at bare $HOME with no scope/env/arg **When** a caller that only catches ImportError invokes it **Then** it returns a path (no RuntimeError escapes). **Given** init_db targeting $HOME/.coding-os/coding-os.db **When** it runs **Then** it refuses (guard at the mkdir chokepoint). **Given** a task with a ## Work Log before a later section edited via the board drawer **When** saved **Then** the Work Log stays in place and no phantom body edit is recorded. **Given** cos_search with default include_body=False **When** it returns results **Then** no content field is built or popped.

## Work Log
- 2026-07-04 [claude]: Edit database.py
- 2026-07-04 [claude]: Edit database.py
- 2026-07-04 [claude]: Edit database.py
- 2026-07-04 [claude]: Edit database.py
- 2026-07-04 [claude]: Edit database.py
- 2026-07-04 [claude]: Edit test_db.py
- 2026-07-04 [claude]: Edit test_db.py
- 2026-07-04 [claude]: Edit hub-architecture.md
- 2026-07-04 [claude]: Edit CosBoardPage.tsx
- 2026-07-04 [claude]: Edit CosBoardPage.tsx
- 2026-07-04 [claude]: Edit mcp_tools.py
- 2026-07-04 [claude]: Edit mcp_tools.py
- 2026-07-04 [claude]: Edit task-lifecycle.md
- 2026-07-04 [claude]: Edit test_mcp_tools.py
- 2026-07-04 [claude]: Edit memory.py
- 2026-07-04 [claude]: Edit memory.py
- 2026-07-04 [claude]: Edit memory.py
- 2026-07-04 [claude]: Applied all 8 verified /code-review findings. database.py: reverted the resolve_db_path RuntimeError (#1 —…
- 2026-07-04 [claude]: committed 955678c4 · 8 files
- 2026-07-04 [claude]: Status transitioned to complete via cos task-done.
