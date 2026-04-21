<!-- domain:ALL | layer:reference | ssot:true | updated:2026-04-18 -->
# Phase K — DB Abstraction & Gated Postgres Backend

Purpose: Define the trigger conditions and migration path for moving from SQLite to Postgres/pgvector — and explicitly NOT invoke that path until measured metrics demand it.
Read when: Considering adding a concurrent-writer scenario, scaling past ~30 000 chunks, or investigating retrieval latency above 150 ms.
Read next: [docs/phase-g-brain-hardening-plan.md](./phase-g-brain-hardening-plan.md) §G.11 (precision tracker which also feeds scale metrics), [core/thinking_os/db.py](../core/thinking_os/db.py).

## Why (honest framing)

**The default answer to "should we use Postgres?" is NO until proven otherwise.** SQLite with FTS5, 17 explicit indexes, and WAL mode handles single-MCP-server workloads at coding-os's realistic scale (≤50k document chunks + ≤10k learned patterns + ≤5k task rows) with query latency typically under 20 ms. Adding Postgres before that threshold costs operational complexity (deploy, pool, backup, migration) without buying runtime benefit.

However, we also don't want to paint ourselves into a corner. Phase K ships the **abstraction and the metric gate** now so that the day we cross the threshold, the switch is a weekend's work instead of a month's.

## Principles

- **P-K-1: Don't build what we don't measure needing.** K.0 and K.1 ship now. K.2 (Postgres backend) ships only when the gate condition is true for 7 consecutive days.
- **P-K-2: Abstraction is not free.** Keep it minimal — only the operations that differ between backends (similarity search, FTS, concurrent transactions). All CRUD stays on plain `sqlite3.Connection`.
- **P-K-3: Performance budget is the signal, not feature envy.** Adding Postgres because "SQL is more powerful" is featuritis. Adding it because `cos_health` reports median retrieval latency > 150 ms for 7 days straight is engineering.
- **P-K-4: Migration path tested, not assumed.** Before K.2 ships, `scripts/migrate_sqlite_to_postgres.py` is written and round-trip tested against a golden DB.

## Phase K Roadmap

| Slice | Scope | Trigger | LOC |
|---|---|---|---|
| **K.0** | `docs/phase-k-db-abstraction-plan.md` (this doc) — trigger conditions, migration outline, decision log | now | 0 code |
| **K.1** | `tools/_db.py` — thin protocol (`DBAdapter` Protocol) wrapping similarity_search + fts_match + audit_log writes. All tools refactored to use it | now (when confirming no over-engineering) | ~200 |
| **K.2** | `tools/_db_postgres.py` — pgvector-backed adapter with HNSW indexing | **gated** | ~400 |
| **K.3** | `scripts/migrate_sqlite_to_postgres.py` — one-shot migration with round-trip verification | ships with K.2 | ~300 |
| **K.4** | Consumer-project docs update: "you can opt into Postgres via `cos init --db postgres:...`" | ships with K.2 | 0 code |

## Gate Condition for K.2

K.2 ships **only** when ALL of these are true for 7 consecutive days:

1. `cos_health.rag.document_chunks_count > 30000`
2. `cos_health.retrieval.median_latency_ms > 150` (measured by a new cos_health field — add to G.11 tracker)
3. The project is **not** hitting a resource cliff (e.g. laptop RAM exhausted loading the model — in that case the fix is a smaller model, not Postgres)
4. A second writer is needed OR you're on a multi-process deployment — single-process stays on SQLite regardless of size

Failure to meet any condition → delay K.2.

**Anti-pattern watch:** if we reach K.2 at say 10 000 chunks, that's a signal something else is wrong (inefficient indexing, runaway observation capture, missing ANN). Diagnose before scaling the backend.

## K.0 — Decision Log

- **2026-04-18:** Phase K.0 shipped. Document chunks in production coding-os repo: 2. Median query latency: <5 ms. Postgres backend not justified by 10× margin on every metric.
- Future entries: when thresholds move, note here with date + metrics.

## K.1 — DBAdapter Protocol (if we ship it)

**Decision gate for K.1 itself:** ship K.1 only if we find ourselves about to write a second SQLite-specific code path. Otherwise, YAGNI.

**Sketch (if needed):**

```python
class DBAdapter(Protocol):
    def connect(self) -> Any: ...
    def similarity_search(
        self, query_vec: bytes, source_tables: list[str],
        limit: int, threshold: float,
    ) -> list[dict]: ...
    def fts_match(
        self, table: str, query: str, limit: int,
    ) -> list[dict]: ...
    def append_audit(
        self, *, actor: str, action: str, source_table: str,
        source_id: Optional[int], reason: Optional[str],
    ) -> Optional[int]: ...
```

**Concrete adapters:** `SQLiteAdapter` (wraps current code — no behavior change); `PostgresAdapter` (K.2).

**Rollout:** touch only the tools that care about backend details (memory, docs, retrieve, retrieval_quality). Everything else keeps using `sqlite3.Connection` unchanged.

## K.2 — Postgres Backend (gated)

Writing this only after the gate is true. Planning shape:

- pgvector extension + HNSW index on `embeddings.embedding`
- FTS via Postgres built-in `tsvector` or stick with FTS5-style virtual tables via third-party
- Connection pool: `psycopg_pool` with small bounded size (5-10 connections)
- Migration alias layer: every query goes through `DBAdapter.similarity_search` so no SQL literal changes
- Concurrent safety: explicit SELECT FOR UPDATE on mutation paths

## K.3 — Migration Script

When K.2 ships, K.3 provides:

```bash
scripts/migrate_sqlite_to_postgres.py --from .coding-os/thinking-os.db \
                                       --to postgres://user@host/coding_os \
                                       --verify
```

1. Read each table from SQLite, stream rows to Postgres
2. Handle BLOB embedding column (SQLite bytes → Postgres bytea → pgvector cast)
3. Rebuild FTS indexes + HNSW indexes
4. Verify: row counts match; sample 100 retrieval queries return same top-5 IDs ±1

## Risks & Mitigations

- **R-K-1: Premature abstraction.** Mitigation: K.1 ships only when concretely needed.
- **R-K-2: Postgres ops are heavier than agents' tolerance.** Mitigation: K.2 never becomes the default. `cos init` keeps SQLite as default forever; Postgres is opt-in.
- **R-K-3: Migration data loss.** Mitigation: K.3 round-trip verification + dry-run mode + automatic SQLite backup before migration.
- **R-K-4: ANN recall worse than brute force.** Mitigation: pgvector HNSW is tunable (`ef_search`). Benchmark before shipping.

## Ship Checklist

- [x] K.0 this doc exists, decision log entry for 2026-04-18 present
- [ ] K.1 (IF and only IF concretely needed): `tools/_db.py` introduces `DBAdapter`, tests cover both backends
- [ ] K.2 (GATED): pgvector backend + HNSW index, benchmark report in decision log
- [ ] K.3 (with K.2): migration script + round-trip test
- [ ] K.4: consumer docs + `cos init --db` flag
