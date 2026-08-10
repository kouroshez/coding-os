---
id: TASK-926
title: "refactor: split database.py (2917 lines) into paths, the append-only ledger, and a runtime facade"
swimlane: core
kind: refactor
epic: null
labels: [tech-debt, database, ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-08-10
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-926: refactor: split database.py (2917 lines) into paths, the append-only ledger, and a runtime facade

**Outcome (one sentence):** src/core/thinking_os/database.py drops from 2917 to ~450 lines by moving project-root/path resolution into _db_paths.py and the append-only migration ledger into _db_migrations.py, with the public surface (project_root, resolve_db_path, init_db, run_migrations, MIGRATIONS, has_* probes) still importable from database.

## Read First
- docs/architecture/raptor-consolidation.md
- src/core/thinking_os/database.py
- docs/engineering/ci-gates.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the split has landed **When** `python src/core/thinking_os/server.py --test` runs **Then** it exits 0.
**Given** the split has landed **When** `uv run --extra rag pytest src/core/thinking_os/tests/test_db.py -q` runs **Then** every migration test passes against its new import path.
**Given** the migration ledger stays over the 500-line backstop **When** ci-gates.md is read **Then** a recorded exception explains why an append-only ledger is not split.

## Work Log
