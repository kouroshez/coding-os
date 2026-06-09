<!-- domain:ALL | layer:engineering | ssot:true | updated:2026-04-19 -->
# Graph-OS Query Guide

> P: Decision guide for picking the right `cos_graph_*` tool per query and slotting it into the three-layer retrieval contract.
> R: Routing an agent flow that touches the graph (rename, impact analysis, dependency walk).
> S: Internals of a single tool — see [graph-use-cases.md](graph-use-cases.md).
> N: [graph-hallucination-cures.md](graph-hallucination-cures.md), [graph-use-cases.md](graph-use-cases.md)

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

> When to use each `cos_graph_*` tool, and which three-layer retrieval
> slot it occupies. Read this before routing any agent flow that touches
> the knowledge graph subsystem.

## Three-layer retrieval recap

| Layer | Question | Tools |
|---|---|---|
| 1. Memory | "Have I solved this before?" | `cos_search`, `cos_timeline`, `cos_details`, `cos_learn_suggest` |
| 2. Docs | "What does the spec say?" | `cos_doc_search` |
| 3. **Graph** | **"What is connected to what?"** | **`cos_graph_*`** |

## Tool cheat sheet

| Question | Tool |
|---|---|
| What depends on X? | `cos_graph_impact(uid, direction="downstream")` |
| Who calls X? | `cos_graph_references(uid)` |
| Where is X used + surrounding context? | `cos_graph_context(uid_or_name, depth=1)` |
| Trace execution from entry point | `cos_graph_trace(entry_uid)` |
| Find symbol by label | `cos_graph_query(q)` |
| Something semantically similar? | `cos_graph_similar(uid)` |
| Shortest path between X and Y? | `cos_graph_path(X, Y)` |
| API surface (HTTP, MCP, gRPC, events) | `cos_graph_contracts()` |
| Plan before rename | `cos_graph_rename_plan(uid, new_name)` |
| Pre-commit: what changes broke? | `cos_graph_detect_changes(files=[...])` |
| Visualise | `cos_graph_export(format="mermaid"|"json"|"dot")` — `max_nodes` default 500 for agents, G35 hard-caps at 2000. `{nodes, edges}` envelope uses the 5 MB graph-subgraph budget (see [mcp-error-envelope.md § Token budget tiers](mcp-error-envelope.md#token-budget-tiers)) so Hub UI gets the full tree; coherent-subgraph trim kicks in only above the OOM ceiling. |

## Routing decision

1. **Exact identifier** (function / task id / file) → Grep or `cos_graph_query`.
2. **Conceptual question** → `cos_doc_search`.
3. **"Have I seen this?"** → `cos_search`.
4. **"What is connected?"** → `cos_graph_*`.

Each envelope carries `data.meta.layer` so consumers can audit which
layer answered.

### `cos_graph_similar` — persisted-embedding fast path

`cos_graph_similar` prefers persisted graph_node vectors when available:
`reindex_all` embeds the meaningful kinds (function · method · class ·
route · mcp_tool · doc_heading) into `embeddings(source_table='graph_nodes')`,
and the tool ranks the **full pool** with a single query encode
(`meta.scorer="persisted-embeddings"`, ~25 ms vs ~1800 ms for the legacy
per-candidate path). When no persisted vectors exist (or the embedding
model is unavailable) it transparently falls back to the on-the-fly
difflib baseline (`meta.scorer="bge-m3+difflib-blend"` /
`"difflib-baseline"`). Raw cosine and the legacy blended score live on
different scales, so the persisted path caps its floor at
`_PERSISTED_COSINE_FLOOR` (0.25) — a `confidence_min` above that no longer
suppresses the fast path; `meta.floor` reports the effective value. Run
`cos brain --reindex` (or `python -m embeddings --reindex`) to populate
the vectors after a bulk graph change.

## Common failure modes

- `fail("unavailable", ...)` with `retryable=true` — backend missing.
  Retry after `cos graph-reindex` / server restart.
- `meta.dim_mismatch_skipped>0` (embedding-aware tools) — BGE-M3
  migration still in progress; fallback search may be degraded.
- `meta.backend_fallback` — reserved for a future graph-native store;
  currently always absent/false. SQLite is the sole backend (Kùzu retired
  2026-05-18, ADR-0002), so this is a no-op signal today.

## Formula linkage

Every formula in `docs/code-os-core-docs/thinkingos-formulas/formulas-en.md`
that mentions a graph has a specific `cos_graph_*` call behind it:

| Formula | Tool |
|---|---|
| F1 Research | `cos_graph_context(entry_point)` |
| F2 Dependency Map | `cos_graph_impact(uid)` |
| F3 API Design | `cos_graph_references(handler)` |
| F4 Docs | `cos_graph_contracts()` |
| F5 Pre-Implementation | `cos_graph_context(file)` |
| F6 Regression Tests | `cos_graph_detect_changes(files=...)` |
| F7 Fault Isolation | `cos_graph_trace(entry_uid)` |
| F8 Auth Audit | `cos_graph_references("verify_auth")` + `cos_graph_contracts()` |
| F9 Release Gate | `cos_graph_contracts()` + `cos_graph_detect_changes("HEAD~1..HEAD")` |
| F10 Tracing | `cos_graph_trace` |
| F11 Refactor Plan | `cos_graph_impact` + `cos_graph_similar` |

## Skills

- `graph-explorer` — the canonical entry skill (`src/core/skills/graph-explorer/SKILL.md`).
- `codebase-explorer` — pairs with graph-explorer; codebase-explorer is
  better for conceptual reading, graph-explorer is better for
  symbol-precise lookups.

## Commands

- `cos graph-reindex` — rebuild the graph from scratch. Shows a live
  per-file progress bar on an interactive terminal (auto-hidden when
  stdout is piped/CI); `--workers N` parallelises and `--force` bypasses
  the content-hash cache. The final line reports
  `processed/skipped/errors/duration`.
- `cos graph-query "<phrase>"` — convenience CLI wrapper over
  `cos_graph_query`.
- `cos graph-viz [--root <uid>]` — produce the HTML viewer (plan
  §15 / I.10).
