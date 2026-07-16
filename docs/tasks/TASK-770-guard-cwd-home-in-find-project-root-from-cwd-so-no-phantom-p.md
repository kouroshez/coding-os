---
id: TASK-770
title: "Guard cwd==$HOME in _find_project_root_from_cwd so no phantom project DB is minted at the global hub dir"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-07-04
started: 2026-07-03
completed: 2026-07-03
agent_session: ses-claude-20260703-210450-473d
depends_on: []
blocked_by: []
references: []
---
# TASK-770: Guard cwd==$HOME in _find_project_root_from_cwd so no phantom project DB is minted at the global hub dir

**Outcome (one sentence):** _find_project_root_from_cwd never resolves a project root to $HOME; resolve_db_path fails loud instead of minting $HOME/.coding-os/coding-os.db; the existing 0-row stray home DB is removed; the address-space split is documented.

## Read First
- src/core/thinking_os/database.py
- src/core/hooks/cos-env.sh
- docs/engineering/hub-architecture.md

## Repro Steps
cd ~ with no COS_DB_PATH and import database → resolve_db_path() returns $HOME/.coding-os/coding-os.db and init_db there mints a phantom 0-row project DB inside the global hub state dir.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a process whose cwd is exactly $HOME with no COS_DB_PATH and no bound scope **When** it calls resolve_db_path() **Then** it raises rather than returning $HOME/.coding-os/coding-os.db. **Given** a subdir under $HOME with no project .coding-os/ **When** _find_project_root_from_cwd runs **Then** it still returns cwd (unchanged). **Given** the repo checkout **When** the DB path resolves **Then** it is byte-identical to before.

## Work Log
- 2026-07-04 [claude]: Edit hub-architecture.md
- 2026-07-04 [claude]: Edit database.py
- 2026-07-04 [claude]: Edit database.py
- 2026-07-04 [claude]: Edit database.py
- 2026-07-04 [claude]: Edit database.py
- 2026-07-04 [claude]: Edit database.py
- 2026-07-04 [claude]: Edit database.py
- 2026-07-04 [claude]: Edit test_db.py
- 2026-07-04 [claude]: Chose Path|None finder contract over guarding only resolve_db_path: DEFAULT_DB_PATH consumes the finder directly (12…
- 2026-07-04 [claude]: committed b6ca44af · 3 files
- 2026-07-04 [claude]: Status transitioned to complete via cos task-done.
