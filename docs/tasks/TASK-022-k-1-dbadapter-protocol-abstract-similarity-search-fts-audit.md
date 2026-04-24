---
id: TASK-022
title: "K.1  DBAdapter Protocol — abstract similarity_search + fts + audit"
swimlane: thinking-os
kind: refactor
epic: phase-k
labels: [db-abstraction]
status: icebox
priority: P3
appetite: "1d"
created: 2026-04-20
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-022: K.1 — DBAdapter Protocol

**Outcome (one sentence):** A minimal `DBAdapter` Protocol lands in `core/thinking_os/tools/_db.py` abstracting **only** `similarity_search`, `fts_match`, and `append_audit`; a default `SQLiteAdapter` wraps the current code with zero behaviour change, unblocking TASK-023 (Postgres adapter) *without* introducing premature abstraction elsewhere.

## Read First

- [docs/phase-k-db-abstraction-plan.md §K.1](../phase-k-db-abstraction-plan.md) — SSOT for this slice (including the Protocol sketch on lines 55–69 and YAGNI rule: ship only if a second SQLite-specific code path is about to be written).
- [core/thinking_os/tools/memory.py](../../core/thinking_os/tools/memory.py) + [docs.py](../../core/thinking_os/tools/docs.py) + [retrieve.py](../../core/thinking_os/tools/retrieve.py) — the three tools that currently call `sqlite3` directly for similarity/FTS/audit; refactor targets.
- [core/thinking_os/db.py](../../core/thinking_os/db.py) — connection helpers + audit append (reuse, don't duplicate).

## Decision gate (honour the SSOT)

Per the plan: **do not ship K.1 speculatively.** Ship only when we are about to write a second SQLite-specific code path (i.e. concurrently with starting TASK-023). If no trigger yet, keep this task in icebox.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** the current SQLite-only code in `memory.py`, `docs.py`, `retrieve.py`
  **When** K.1 lands
  **Then** those three modules import from `tools._db` and call `adapter.similarity_search / fts_match / append_audit` — no other tool is touched.
- **Given** the existing SQLite behaviour
  **When** the test suite runs
  **Then** every existing test passes unchanged. Zero behaviour change.
- **Given** the Protocol
  **When** a new subclass `FakeAdapter` is written in tests
  **Then** it can fully substitute `SQLiteAdapter` for unit tests — proving the Protocol is concrete enough.
- **Tests:** `core/thinking_os/tests/test_db_adapter.py` covers Protocol contract + `SQLiteAdapter` parity; existing retrieval + docs tests keep passing.

## Implementation Notes

- Protocol signature exactly as in the plan (lines 55–69). Do NOT add extra methods.
- `SQLiteAdapter` simply wraps current helpers; no new SQL.
- Audit append keeps the same append-only table and schema.

## Dependencies

- **Depends on:** nothing.
- **Unblocks:** TASK-023 (Postgres adapter is only writeable when this contract exists).

## Work Log
