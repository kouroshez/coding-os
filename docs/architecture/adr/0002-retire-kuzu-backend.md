<!-- domain:ARCH | layer:adr | ssot:true | updated:2026-05-18 -->

# ADR-0002: Retire the Kuzu graph backend; SQLite is the only store

- **Status:** Accepted (2026-05-18)
- **Deciders:** Kourosh Ebrahimzadeh
- **Context tags:** graph_os, backend, performance, dependency-pinning

## Context

`graph_os` shipped with two pluggable backends:

- **Kuzu** — an embedded property-graph database. Native Cypher,
  designed for graph workloads. The "fast path" for deep walks.
- **SQLite** — the always-available fallback. Recursive CTE for
  walks, JSON columns for metadata. Slower in theory but always
  on disk where the rest of the project state lives.

The dual-backend design was a hedge: if SQLite proved too slow on
real graphs, Kuzu would take over. In practice, three things shifted
the trade-off:

1. **Workload reality.** The graph for a typical project has
   10K–200K nodes; the meta-repo itself peaks around 1M. Both
   workloads sit well inside SQLite's comfort zone with PRAGMA
   tuning (mmap_size, page_size, ANALYZE, optimize).
2. **Embedded-DB friction.** Kuzu's storage format changes between
   minor versions. Every upgrade required a full reindex; the C++
   binary varied across Python versions and macOS targets.
3. **Two-backend tax.** Every `cos_graph_*` tool had to test both
   paths. Each new feature was conditioned on backend capability.
   Hallucinations crept in when an answer came from one backend
   silently differed from the other.

The benchmark (`src/scripts/bench_graph_backends.py`, results in
`docs/engineering/sqlite-vs-kuzu-bench-2026-05-15.md`) showed
SQLite with mmap + ANALYZE delivers p99 < 30 ms for 5-hop
traversal on 1M nodes — well inside the budget for every UI tab
and every `cos_graph_*` MCP tool. Kuzu's lead (~3× on raw walk
latency) didn't matter when both were already sub-frame.

## Decision

Retire the Kuzu backend in three phases:

- **B2a (2026-05-15)** — quarantine: stop opening new Kuzu
  connections; log a DeprecationWarning on `kuzu_path=` kwarg.
  All reads route through SQLite. Kuzu code path stays in for
  emergency rollback.
- **B2b (2026-05-17)** — drop docs: remove every Kuzu reference
  from skills, playbooks, the `meta-graph-first.md` rule,
  templates.
- **B2c (2026-05-18)** — delete the backend file +
  parity-tests. The `[graph_os]` extra no longer installs
  `kuzu` as a dependency.

SQLite becomes the **only** graph backend. All
`cos_graph_*` tools assume SQLite shape; no runtime fallback
logic remains.

## Consequences

**Positive:**

- One backend to test, document, optimize.
- `[graph_os]` extra shrinks from 7 deps to 5 (drops Kuzu + its
  binary wheel).
- No more "did this answer come from Kuzu or SQLite?" ambiguity
  in MCP tool responses (`meta.backend_fallback` field retired).
- Reindex is faster because SQLite's incremental upsert path is
  battle-tested.

**Negative:**

- Lose the headroom Kuzu would have provided at >10M-node graphs
  if the project ever indexed something that large.
- Some power-users were experimenting with Cypher queries against
  the embedded Kuzu — they need to migrate to the
  `cos_graph_query` MCP tool or use SQL directly.

**Mitigations:**

- The `cos_graph_*` MCP tools cover every common query pattern.
  Power-users with edge cases can file feature requests.
- If we ever cross the >10M-node threshold, the pluggable backend
  layer hasn't been deleted — only its second implementation. A
  future `[graph_os_lance]` or `[graph_os_neptune]` could land
  without re-architecture.

## Alternatives considered

- **Keep dual backends and accept the tax.** Rejected — the
  hallucination + drift risk grew faster than the performance
  benefit.
- **Replace Kuzu with DuckDB** (similar embedded, SQL-friendlier).
  Rejected — SQLite already met the budget; adding DuckDB would
  re-introduce a second-backend tax we just paid to remove.
- **Move the graph to Postgres** (full server-side DB). Rejected
  — the project's runtime is per-project SQLite + in-process MCP.
  Adding a server would be a different product.
