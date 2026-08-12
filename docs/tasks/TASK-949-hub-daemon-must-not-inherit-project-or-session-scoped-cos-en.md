---
id: TASK-949
title: "Hub daemon must not inherit project- or session-scoped COS_* env"
swimlane: cli
kind: bug
epic: null
labels: [ready]
status: testing
priority: P0
appetite: 1d
created: 2026-08-12
started: 2026-08-12
completed: null
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-949: Hub daemon must not inherit project- or session-scoped COS_* env

**Outcome (one sentence):** cos hub start spawns the daemon with project- and session-scoped COS_* vars stripped, so the multi-project Hub resolves every project's state from the registry per request instead of being pinned to whatever shell started it.

## Read First
- docs/engineering/state-files.md
- src/cli/hub_commands.py
- src/core/web/_project_context.py

## Repro Steps
Export COS_STATE_DIR=/tmp/x/.coding-os (as a leaked pytest fixture env does), run `cos hub start`, then GET /api/config/adapters: adapters report installed=false and health=disabled because project_root() resolved to /tmp/x, where no .coding-os.yaml or hub-settings.json exists. Observed live on pid 16917 with COS_STATE_DIR=/private/tmp/pytest-of-ciro/pytest-639/log_isolate905/.coding-os.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a shell exporting COS_STATE_DIR/COS_DB_PATH/COS_AGENT_DIR/COS_PANEL_DIR pointing at an unrelated directory
**When** `cos hub start` spawns the daemon and a client requests /api/config/adapters for the coding-os project
**Then** the response reports installed=true for the adapters listed in .coding-os.yaml and supervision health reflects .coding-os/hub-settings.json, because the daemon's environment carries none of those project-scoped vars.

## Work Log
- 2026-08-12 [claude]: Edit state-files.md
- 2026-08-12 [claude]: Edit state-files.md
- 2026-08-12 [claude]: Edit cqs.md
- 2026-08-12 [claude]: Plan: share one SSOT env-scope tuple pair in _db_paths.py (beside the project-root resolver it undoes) rather than a…
- 2026-08-12 [claude]: Edit _db_paths.py
- 2026-08-12 [claude]: Edit database.py
- 2026-08-12 [claude]: Edit database.py
- 2026-08-12 [claude]: Edit hub_commands.py
- 2026-08-12 [claude]: Edit hub_commands.py
- 2026-08-12 [claude]: Edit hub_commands.py
- 2026-08-12 [claude]: Edit hub_commands.py
- 2026-08-12 [claude]: Edit scheduled.py
- 2026-08-12 [claude]: Edit scheduled.py
- 2026-08-12 [claude]: Edit test_hub_staleness.py
- 2026-08-12 [claude]: Edit hub_commands.py
- 2026-08-12 [claude]: Edit test_hub_staleness.py
- 2026-08-12 [claude]: Verified live: hub started from a shell exporting…
- 2026-08-12 [claude]: Matrix green: tests/test_cli.py 294 passed; src/core/thinking_os/tests/ 1572 passed (not slow); server.py --test ok;…
