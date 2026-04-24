---
id: TASK-024
title: "K.3  sqlite → postgres migration script + round-trip"
swimlane: thinking-os
kind: feature
epic: phase-k
labels: [db-abstraction, migration]
status: icebox
priority: P3
appetite: "1d"
created: 2026-04-20
started: null
completed: null
agent_session: null
depends_on: [TASK-023]
blocked_by: []
references: []
---

# TASK-024: K.3 — sqlite → postgres migration script

**Outcome (one sentence):** `scripts/migrate_sqlite_to_postgres.py --from .coding-os/thinking-os.db --to postgres://… --verify` streams every table + BLOB embedding column into Postgres, rebuilds HNSW + FTS indexes, and round-trip verifies that 100 sampled retrieval queries return the same top-5 IDs (±1) as the source SQLite — ships alongside TASK-023 and is a hard prerequisite for shipping K.2 to any consumer.

## Read First

- [docs/phase-k-db-abstraction-plan.md §K.3](../phase-k-db-abstraction-plan.md) — SSOT for the migration outline + round-trip recipe.
- [core/thinking_os/tools/_db.py](../../core/thinking_os/tools/_db.py) (post TASK-022) — Protocol used by both sides so the verification loop is identical.
- [core/thinking_os/db.py](../../core/thinking_os/db.py) — authoritative migration version + table list.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** a SQLite DB with representative data (≥ 1k docs + ≥ 1k memory rows)
  **When** `migrate_sqlite_to_postgres.py --from … --to … --verify` runs
  **Then** exit 0, row counts match per table (printed diff table), and the 100-sample retrieval comparison reports ≥ 99 matches out of 100 for top-5 ID overlap.
- **Given** `--dry-run`
  **When** run
  **Then** no rows are written; the script prints the plan (tables, row counts, index ops).
- **Given** the source DB about to be migrated
  **When** the script starts
  **Then** an automatic backup `.coding-os/thinking-os.db.bak.YYYYMMDD-HHMMSS` is created first — no-op if already exists in the last 10 minutes.
- **Given** a BLOB embedding column
  **When** migrated
  **Then** SQLite bytes → Postgres `bytea` → pgvector cast yields the same float32 vector; verified with a checksum (e.g. first-element float equality on 100 samples).
- **Given** a network failure mid-migration
  **When** it happens
  **Then** the script supports `--resume` by checkpointing per-table completion in a control table in Postgres; re-run picks up where it left off.
- **Tests:** `tests/test_migrate_sqlite_to_postgres.py` with a tmp Postgres instance (skip gracefully when `COS_TEST_POSTGRES_URL` is unset) covers happy path + dry-run + resume.

## Implementation Notes

- Use `psycopg.copy_from` (COPY protocol) for bulk rows — order of magnitude faster than INSERT.
- Embedding BLOB handling: read bytes → `numpy.frombuffer` to validate → `cast(%s::vector)` on the Postgres side.
- Rebuild indexes **after** bulk load (faster than incremental).
- Never delete the source SQLite; rollback = point `cos init` back at the `.bak` file.

## Dependencies

- **Depends on:** TASK-023 (pg adapter must be shippable before migration is meaningful).
- **Unblocks:** TASK-025 (consumer docs).

## Work Log
