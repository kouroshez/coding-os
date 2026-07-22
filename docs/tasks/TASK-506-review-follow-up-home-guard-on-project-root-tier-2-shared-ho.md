---
id: TASK-506
title: "Review follow-up: $HOME guard on project_root() tier-2 + shared hook-helper resolver (no DB import on hot path)"
swimlane: core
kind: bug
epic: null
labels: [state-resolution, review-followup, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-21
started: 2026-06-21
completed: 2026-06-21
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-506: Review follow-up: $HOME guard on project_root() tier-2 + shared hook-helper resolver (no DB import on hot path)

**Outcome (one sentence):** Two real issues from the TASK-498 max-effort review are fixed: (1) database.project_root() tier-2 no longer returns $HOME when COS_STATE_DIR is an absolute path equal to $HOME/.coding-os (the global hub, set by cos hub) — it falls through to the marker-walk instead; (2) the 4 hook helpers (task_sync, work_log_append, validate_task_frontmatter, wip_limit_check) share one resolve_project_root() in _helpers/_paths.py that resolves COS_PROJECT_ROOT > absolute COS_STATE_DIR parent (no import) > lazy database.project_root() > cwd — removing the duplicated try/except idiom and the ~20-60ms thinking_os.database import on the hot per-hook path (COS_STATE_DIR is set by cos-env.sh, so the import almost never runs).

## Read First
- src/core/thinking_os/database.py
- src/core/hooks/_helpers/task_sync.py
- docs/engineering/state-files.md

## Repro Steps
Set COS_STATE_DIR=$HOME/.coding-os and call database.project_root() → today returns $HOME (global hub) instead of walking. And: grep the 4 hook helpers shows 4 copy-paste try/except blocks each importing thinking_os.database (~20-60ms) on every hook fire even though COS_STATE_DIR is already set by cos-env.sh.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** COS_STATE_DIR=$HOME/.coding-os (absolute, == global hub), **When** database.project_root() is called, **Then** it does NOT return $HOME; it falls through to the marker-walk (which has its own $HOME hard-stop).
**Given** a hook helper runs with COS_STATE_DIR set to an absolute <root>/.coding-os and thinking_os.database NOT yet imported, **When** it resolves the project root, **Then** it returns <root> WITHOUT importing thinking_os.database (verified: no database import on that path).
**Given** thinking_os.database import fails, **When** resolve_project_root() runs with no COS_PROJECT_ROOT/COS_STATE_DIR, **Then** it falls back to cwd (fail-open, no crash).
**Given** the existing suites, **When** the fix lands, **Then** test_db.py, test_hooks.py, board_os, and cli remain green and a new test covers the tier-2 $HOME guard.

## Work Log
- 2026-06-21 [claude]: Edit database.py
- 2026-06-21 [claude]: Edit _paths.py
- 2026-06-21 [claude]: Edit task_sync.py
- 2026-06-21 [claude]: Edit work_log_append.py
- 2026-06-21 [claude]: Edit validate_task_frontmatter.py
- 2026-06-21 [claude]: Edit wip_limit_check.py
- 2026-06-21 [claude]: Edit test_db.py
- 2026-06-21 [claude]: Edit _probe_task506.py
- 2026-06-21 [claude]: Fix 1: database.project_root() tier-2 now $HOME-guards an absolute COS_STATE_DIR (==$HOME/.coding-os hub) and falls…
- 2026-06-21 [claude]: commit 78d4ef160d — fix(state-resolution): $HOME-guard project_root tier-2 + shared hook resolver
