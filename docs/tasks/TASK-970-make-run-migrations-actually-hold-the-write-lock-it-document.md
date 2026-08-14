---
id: TASK-970
title: "Make run_migrations actually hold the write lock it documents"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [database, concurrency, P0, ready]
status: complete
priority: P0
appetite: 1d
created: 2026-08-14
started: 2026-08-14
completed: 2026-08-14
agent_session: ses-claude-20260814-120316-413b
depends_on: []
blocked_by: []
references: []
---
# TASK-970: Make run_migrations actually hold the write lock it documents

**Outcome (one sentence):** Concurrent processes opening the same coding-os.db either apply a migration under a held write lock or wait for the holder, never both run unlocked against a half-migrated schema.

## Read First
- docs/governance/critical-rules.md § Rule 9
- src/core/thinking_os/database.py:242-300

## Repro Steps
`BEGIN IMMEDIATE` then `_ensure_version_table()` (reached via get_schema_version) calls conn.commit(), which ends the transaction: in_transaction goes True -> False and a second sqlite3 connection acquires BEGIN IMMEDIATE on the same file. Additionally, `contextlib.suppress(sqlite3.OperationalError)` around BEGIN IMMEDIATE turns a SQLITE_BUSY into an unlocked migration run, and conn.executescript() issues its own implicit COMMIT.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a connection inside run_migrations, **When** it reads the schema version, **Then** conn.in_transaction stays True for the whole migration loop.
- **Given** two processes calling run_migrations on one DB concurrently, **When** one holds the lock, **Then** the other waits and re-reads the version rather than proceeding unlocked.
- **Given** BEGIN IMMEDIATE fails with SQLITE_BUSY past the retry budget, **When** run_migrations returns, **Then** it did not apply any migration outside a transaction.
- **Given** N processes racing on a fresh DB, **When** all finish, **Then** the schema version is the target and no duplicate/partial migration was applied.

## Work Log
- 2026-08-14 [claude]: Edit critical-rules.md
- 2026-08-14 [claude]: Edit database.py
- 2026-08-14 [claude]: Edit database.py
- 2026-08-14 [claude]: Edit verify_script_split.py
- 2026-08-14 [claude]: Edit database.py
- 2026-08-14 [claude]: Edit database.py
- 2026-08-14 [claude]: Edit database.py
- 2026-08-14 [claude]: Edit database.py
- 2026-08-14 [claude]: Edit database.py
- 2026-08-14 [claude]: Edit test_db_migration_lock.py
- 2026-08-14 [claude]: Edit test_db_migration_lock.py
- 2026-08-14 [claude]: Edit test_db_migration_lock.py
- 2026-08-14 [claude]: Edit msg4.txt
- 2026-08-14 [claude]: commit 864cb53590 — fix(db): hold the migration write lock for the whole apply loop
- 2026-08-14 [claude]: Fixed in 864cb535: version read no longer re-enters the committing _ensure_version_table, BEGIN IMMEDIATE now waits…
- 2026-08-14 [claude]: Status transitioned to complete via cos task-done.
