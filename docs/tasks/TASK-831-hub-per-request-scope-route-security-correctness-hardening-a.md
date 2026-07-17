---
id: TASK-831
title: "Hub per-request scope + route security/correctness hardening (audit remediation)"
swimlane: core
kind: bug
epic: null
labels: [hub, project-scope, audit, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-07-17
started: 2026-07-17
completed: 2026-07-17
agent_session: ses-claude-20260717-014556-89d0
depends_on: []
blocked_by: []
references: []
---
# TASK-831: Hub per-request scope + route security/correctness hardening (audit remediation)

**Outcome (one sentence):** Every Hub backend route honors the per-request project scope (never ambient $COS_* env) and closes the confirmed security/correctness defects from the hub audit.

## Read First
- src/core/web/routes/health.py
- src/core/web/_project_context.py
- src/core/thinking_os/database.py

## Repro Steps
Start hub from coding-os. curl /api/p/streamos/health -> file_index_state_rows=3888 (coding-os's) but /api/p/streamos/health/db -> 637 (streamos's own). Same ambient-env leak class in hooks/logs/observability/_shared. observability timeline session_id is not path-validated.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a /api/p/<slug>/ request **When** it reads DB/logs/hooks/modules **Then** it resolves from the bound project scope, not ambient $COS_DB_PATH/$COS_HOOK_LOG/$COS_LOG_FILE/$COS_STATE_DIR. **Given** observability timeline **When** session_id contains ../ **Then** it is rejected. **Given** two projects each with TASK-050 **When** board auto-spawn fires **Then** the dedup key does not collide across projects. **When** the targeted matrix tests run **Then** they pass.

## Work Log
- 2026-07-17 [claude]: Edit health.py
- 2026-07-17 [claude]: Edit health.py
- 2026-07-17 [claude]: Edit _shared.py
- 2026-07-17 [claude]: Edit hooks.py
- 2026-07-17 [claude]: Edit logs.py
- 2026-07-17 [claude]: Edit observability.py
- 2026-07-17 [claude]: Edit observability.py
- 2026-07-17 [claude]: Edit board.py
- 2026-07-17 [claude]: Edit board.py
- 2026-07-17 [claude]: Edit graph.py
- 2026-07-17 [claude]: Edit test_observability_routes.py
- 2026-07-17 [claude]: Backend cluster committed (83a97294): health/hooks/logs/observability/_shared now honor bound /api/p/<slug>/ scope…
- 2026-07-17 [claude]: commit 25cc454800 — fix(hub-ui): read producer response shapes, send CSRF on mutations, re-scope live logs
- 2026-07-17 [claude]: Status transitioned to complete via cos task-done.
