<!-- domain:ALL | layer:engineering | ssot:true | updated:2026-04-19 -->
# Graph-OS Query Guide

> P: Decision guide for picking the right `cos_graph_*` tool per query and slotting it into the three-layer retrieval contract.
> R: Routing an agent flow that touches the graph (rename, impact analysis, dependency walk).
> S: Designing the graph itself — see [docs/roadmap/graph_os-redesign.md](../roadmap/graph_os-redesign.md).
> N: [docs/engineering/retrieval-routing.md](retrieval-routing.md), [docs/engineering/rename-workflow.md](rename-workflow.md)

> When to use each `cos_graph_*` tool, and which three-layer retrieval
> slot it occupies. Read this before routing any agent flow that touches
> Phase I.

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
| Visualise | `cos_graph_export(format="mermaid"|"json"|"dot")` |

## Routing decision

1. **Exact identifier** (function / task id / file) → Grep or `cos_graph_query`.
2. **Conceptual question** → `cos_doc_search`.
3. **"Have I seen this?"** → `cos_search`.
4. **"What is connected?"** → `cos_graph_*`.

Each envelope carries `data.meta.layer` so consumers can audit which
layer answered.

## Common failure modes

- `fail("unavailable", ...)` with `retryable=true` — backend missing.
  Retry after `cos graph-reindex` / server restart.
- `meta.dim_mismatch_skipped>0` (embedding-aware tools) — BGE-M3
  migration still in progress; fallback search may be degraded.
- `meta.backend_fallback=true` — Kùzu was configured but offline; we
  used SQLite. Deep walks will be slower; consider retrying Kùzu.

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

- `graph-explorer` — the canonical entry skill (`core/skills/graph-explorer/SKILL.md`).
- `codebase-explorer` — pairs with graph-explorer; codebase-explorer is
  better for conceptual reading, graph-explorer is better for
  symbol-precise lookups.

## Commands

- `cos graph-reindex` — rebuild the graph from scratch.
- `cos graph-query "<phrase>"` — convenience CLI wrapper over
  `cos_graph_query`.
- `cos graph-viz [--root <uid>]` — produce the HTML viewer (plan
  §15 / I.10).
