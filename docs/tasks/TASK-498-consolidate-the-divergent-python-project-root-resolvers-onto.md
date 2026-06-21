---
id: TASK-498
title: "Consolidate the divergent Python project-root resolvers onto database.py's canonical walk + add the $HOME hard-stop"
swimlane: core
kind: refactor
epic: null
labels: [state-resolution, consolidation, parity, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-21
started: 2026-06-20
completed: 2026-06-20
agent_session: ses-claude-20260620-185332-bf2c
depends_on: [TASK-490]
blocked_by: []
references: []
---
# TASK-498: Consolidate the divergent Python project-root resolvers onto database.py's canonical walk + add the $HOME hard-stop

**Outcome (one sentence):** The ~9 cwd-only Python project-root resolvers (board_commands._project_root, board_os/mcp_tools._project_root, thinking_os/background._project_root, web/_project_context.current_project_root, hooks/_helpers/{task_sync,validate_task_frontmatter,work_log_append,wip_limit_check}._project_root) and logging_os/config._discover_project_root all delegate to the single canonical resolver thinking_os.database._find_project_root_from_cwd / resolve_db_path; that canonical resolver gains the same explicit $HOME / global-hub hard-stop the shell got in TASK-490. Result: ONE root-resolution contract across the whole codebase, no divergent walks, the global-hub escape closed on the Python side too.

## Read First
- src/core/thinking_os/database.py
- src/cli/board_commands.py
- src/core/logging_os/config.py
- docs/engineering/state-files.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** any of the ~9 cwd-only resolvers invoked from a subdirectory with COS_PROJECT_ROOT and COS_STATE_DIR unset, **When** it resolves the project root, **Then** it returns the same root as `_find_project_root_from_cwd` (walks up for a marked `.coding-os/`), not bare cwd.
**Given** `_find_project_root_from_cwd` walks up and the only `.coding-os/` it would find is `$HOME/.coding-os` (the global hub), **When** resolving, **Then** that path is NOT selected (new hard-stop), matching the shell contract from TASK-490.
**Given** the shell↔Python parity fixtures from TASK-490 extended to exercise the consolidated Python resolvers, **When** run, **Then** every resolver agrees on the root for each fixture tree.
**Given** the existing test suites, **When** the consolidation + $HOME stop land, **Then** `uv run --extra rag pytest src/core/thinking_os/tests/ -q -m 'not slow'`, the board_os suite, and `uv run pytest tests/test_cli.py -q` are all green (no regression in DB-path or root resolution).

## Work Log
- 2026-06-21 [claude]: Edit database.py
- 2026-06-21 [claude]: Edit database.py
- 2026-06-21 [claude]: Edit test_db.py
- 2026-06-21 [claude]: Edit board_commands.py
- 2026-06-21 [claude]: Edit mcp_tools.py
- 2026-06-21 [claude]: Edit background.py
- 2026-06-21 [claude]: Edit background.py
- 2026-06-21 [claude]: Edit _project_context.py
- 2026-06-21 [claude]: Edit task_sync.py
- 2026-06-21 [claude]: Edit work_log_append.py
- 2026-06-21 [claude]: Edit validate_task_frontmatter.py
- 2026-06-21 [claude]: Edit wip_limit_check.py
- 2026-06-21 [claude]: Edit config.py
- 2026-06-21 [claude]: Added canonical database.project_root() + $HOME hard-stop in _find_project_root_from_cwd. Migrated board_commands,…
- 2026-06-21 [claude]: Status transitioned to complete via cos task-done.
