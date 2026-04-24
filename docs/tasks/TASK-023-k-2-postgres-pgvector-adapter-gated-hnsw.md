---
id: TASK-023
title: "K.2  Postgres pgvector adapter (gated, HNSW)"
swimlane: thinking-os
kind: feature
epic: phase-k
labels: [db-abstraction, postgres, gated]
status: icebox
priority: P3
appetite: "2d"
created: 2026-04-20
started: null
completed: null
agent_session: null
depends_on: [TASK-022]
blocked_by: []
references: []
---

# TASK-023: K.2 — Postgres pgvector adapter (gated)

**Outcome (one sentence):** `core/thinking_os/tools/_db_postgres.py` implements the `DBAdapter` Protocol against Postgres + pgvector + HNSW, accessible only when `cos init --db postgres://…` was used, and only after the **gate condition in `docs/phase-k-db-abstraction-plan.md §"Gate Condition for K.2"`** is true for 7 consecutive days.

## Read First

- [docs/phase-k-db-abstraction-plan.md §K.2](../phase-k-db-abstraction-plan.md) — SSOT including the gate rule (chunks > 30k, median latency > 150 ms for 7 days, not a resource cliff, multi-writer scenario).
- [core/thinking_os/tools/_db.py](../../core/thinking_os/tools/_db.py) — the Protocol (shipped by TASK-022).
- [core/thinking_os/db.py](../../core/thinking_os/db.py) — schema to mirror (append-only migrations).
- pgvector docs: `CREATE INDEX … USING hnsw (embedding vector_cosine_ops)`.

## Gate check (MUST be first step in implementation)

Before writing a single line of Postgres code, confirm `cos_health` shows all four gate conditions hold for ≥ 7 consecutive days. If not, **stop and document why K.2 was considered**; append a decision-log entry in the plan doc and close this task as `cancelled` with a clear reason.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** a Postgres 16 instance with the `vector` extension installed
  **When** `cos init --db postgres://user@host/coding_os` runs
  **Then** the full thinking_os schema is created (tables, indexes, HNSW index on `embeddings.embedding`), and a smoke test `cos_health` returns green.
- **Given** a populated DB
  **When** `cos_retrieve("login flow")` is called
  **Then** results are byte-for-byte equivalent to SQLite top-5 ±1 ranking tolerance (documented in the plan).
- **Given** two concurrent writers (MCP + CLI `cos task-create`)
  **When** they write simultaneously
  **Then** no row is lost and no deadlock occurs (explicit `SELECT … FOR UPDATE` on mutation paths).
- **Given** an ANN recall benchmark
  **When** compared to brute-force
  **Then** top-10 recall ≥ 0.95 with default `ef_search`, tunable up to 0.99.
- **Tests:** `tests/test_db_postgres_adapter.py` gated by an env flag (`COS_TEST_POSTGRES_URL`); runs full Protocol contract + a 1k-row benchmark.

## Implementation Notes

1. **Dependency:** add `psycopg[binary]>=3.2` and `psycopg_pool` under a new optional `postgres` extra in `pyproject.toml` — never a required dep.
2. **Connection pool:** 5–10 bounded connections (per the plan).
3. **Schema migrations:** mirror the SQLite migration file list; each migration has a `_pg.sql` sibling. Append-only rule still applies.
4. **FTS choice:** start with Postgres built-in `tsvector` (simpler, good enough); measure before considering external extensions.
5. **Index strategy:** HNSW on embedding + GIN on `tsvector` columns + existing unique/PK indexes mirrored.
6. **`cos init` path:** add `--db` flag that validates the URL and short-circuits to the pg path; default stays SQLite forever.
7. Log a prominent `WARNING: Postgres backend is beta; gate conditions must hold.` on first use.

## Dependencies

- **Depends on:** TASK-022 (Protocol must exist).
- **Unblocks:** TASK-024 (migration script), TASK-025 (consumer docs).

## Work Log
