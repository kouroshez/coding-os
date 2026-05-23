---
name: graph-explorer
tier: exploration
domain: [universal]
description: Navigate the graph_os knowledge graph before editing load-bearing code. Use when tracing dependencies, planning a rename, auditing API surface, or answering "what breaks if I change this?". Pairs with codebase-explorer — graph-explorer wins for symbol-precise queries, codebase-explorer wins for conceptual code-reading.
last_reviewed: "2026-05-11"

---

# graph-explorer

Purpose: Load the Phase I graph_os toolset (`cos_graph_*` MCP tools) and
use it deliberately before any non-trivial code edit. The graph is the
third retrieval layer (CLAUDE.md Three-Layer Retrieval) — use it when
tree-grep or past-memory searches return noise.

Read when: Editing `src/core/**` or `src/cli/**`, producing a rename plan,
auditing API/MCP contracts, answering "what depends on X".

Skip when: You already know the blast radius, or the change is a
self-contained one-file edit with no callers.

## Decision ladder

1. **Need to know "what calls this?"** → `cos_graph_references(uid)`.
2. **Need surrounding context before editing?** → `cos_graph_context(uid_or_name, depth=1)` (Implementer pre-impl step).
3. **Planning a refactor?** → `cos_graph_impact(uid, depth=3)` (Analyst dependency map) groups edges by risk tier.
4. **Renaming a symbol?** → `cos_graph_rename_plan(uid, new_name)` before any `Edit` — returns call-sites, doc refs, tests, string literals.
5. **API / contract audit?** → `cos_graph_contracts(kinds=["http","mcp"])` (Documenter + Deployer).
6. **Tracing a fault?** → `cos_graph_trace(entry_uid)` (Debugger fault isolation step).
7. **"Is anything similar?"** → `cos_graph_similar(uid, top_k=5)`.
8. **Shortest dependency path?** → `cos_graph_path(source, target)`.
9. **Need a diagram?** → `cos_graph_export(format="mermaid", root_uid=...)`.
10. **Pre-commit self-review?** → `cos_graph_detect_changes(files=[...])` — call BEFORE `make verify`.

Every response carries `data.meta.layer="graph"` and `data.meta.backend`
so you can confirm which store answered. When `meta.backend_fallback=true`
the answer came from the SQLite fallback (lower precision on deep walks).

## Coverage contract — never trust a single call blindly

The biggest soundness trap in graph queries is **silent truncation**:
asking "who calls X?" on a 500-caller hub with `limit=100` (the
default) returns 100 rows and **no signal** that 400 more exist —
unless you read the coverage metadata. Every coverage-sensitive tool
exposes it; the rule below is mandatory before you act on a result.

### Signals to read on every response

| Tool | `data.total_count` | Coverage signal in meta | `data.meta.<budget>` |
|---|---|---|---|
| `cos_graph_references` | ✓ | `result_truncated` (limit hit) | `limit` |
| `cos_graph_impact` | – | `walk_truncated` (BFS cap hit) | `visit_limit` · `depth` |
| `cos_graph_context` | – | `walk_truncated` (BFS cap hit) | `visit_limit` · `depth` |
| `cos_graph_path` | – | `walk_truncated` (hop saturation) | `hop_limit` |
| `cos_graph_export` | – | UI badge | `max_nodes` · `max_hops` |

**`result_truncated == true` or `walk_truncated == true` ⇒ the answer
is incomplete. Do NOT proceed on it.**

Why two distinct names? The envelope layer writes `data.meta.truncated`
when *token-budget* trimming kicked in (response too big, tail rows
dropped). Coverage truncation is a different concept — keep the keys
distinct so the agent reacts to the right signal.

### The mandatory 2-step probe → widen workflow

```python
# 1. probe with defaults (cheap, gives you the lay of the land)
r = cos_graph_references(uid)                  # default limit=100
total = r["data"]["total_count"]
shown = r["data"]["count"]

# 2. if incomplete, widen with the actual total
if r["data"]["meta"]["result_truncated"]:
    r = cos_graph_references(uid, limit=total)  # exhaustive
    # alternative: narrow the kinds filter first when total is huge
    # r = cos_graph_references(uid, kinds=["calls"], limit=total)
```

For `cos_graph_impact` and `cos_graph_context`, the budget is
`visit_limit` (default 500 nodes). When `meta.walk_truncated` is true:

```python
# option A — raise the cap deliberately
r = cos_graph_impact(uid, depth=3, visit_limit=5000)

# option B — step DOWN in depth and walk each frontier separately
# (more expensive but produces tier-quality risk grouping)
r1 = cos_graph_impact(uid, depth=1)
for caller in r1["data"]["tiers"]["will_break"]:
    cos_graph_impact(caller["uid"], depth=2)
```

### Per-task-class budget recipes

| Task class | Tool | Budget |
|---|---|---|
| Quick probe ("does X have any callers?") | `cos_graph_references` | `limit=20` |
| Implementation pre-check ("what neighbours?") | `cos_graph_context` | `depth=1` |
| Refactor planning ("what breaks?") | `cos_graph_impact` | `depth=3`, `visit_limit=2000` |
| Rename — must hit every site | `cos_graph_rename_plan` | (exhaustive by design) |
| Security audit — every caller chain | `cos_graph_references` then `cos_graph_impact` per caller | `limit=10_000`, `visit_limit=10_000` |
| Doc cross-reference audit | `cos_graph_references` | `kinds=["references_doc","links_to","cites_heading"]`, `limit=1000` |

**Cost math:** `cos_graph_references` is O(N) with an index; `limit=10_000`
runs in <50 ms on the highest-degree hubs in this repo. There is no
reason to under-budget a coverage-critical sweep. Pay the 50 ms.

### Anti-patterns

- Calling `cos_graph_references(uid)` once and treating the slice as
  complete — without reading `total_count` or `meta.truncated`.
- Setting `limit=20` for a rename or security audit because "small is
  safer" — small **hides** coverage gaps, doesn't prevent them.
- Calling `cos_graph_impact(uid, depth=4)` on a hub and not noticing
  `meta.truncated` — `depth=4` × hub frontier blows past `visit_limit`
  before you reach the interesting frontier.
- Asking the graph the same question twice with the same params hoping
  a different answer comes back — the result is deterministic; widen
  the budget or narrow the filter.

## Enforcement

- `enforce-graph-context.sh` — when editing a file under a path the
  hook treats as load-bearing (the matcher is built into the script —
  there is no `rag-config.yaml::graph.enforce_context_on` key today),
  the hook warns if no `.graph-context-<uid>` marker exists in
  `$COS_AGENT_DIR` for this session.
- `enforce-rename-plan.sh` — if you attempt a multi-file rename-like
  Edit without a prior `cos_graph_rename_plan` in this session, the
  hook warns + suggests the command.

Both hooks default to **warn** so agents discover the graph layer
instead of writing blind. Opt-out with `COS_ENFORCE_GRAPH_CONTEXT=off`
(or `=0`); promote to block with `=strict`. Same for
`COS_ENFORCE_RENAME_PLAN`.

## Auto-reindex contract

The PostToolUse hook `auto-reindex-docs.sh` re-indexes **only the file
just written** via `graph_os.tools.reindex_dispatch.dispatch(path)` —
not the whole repo. The dispatcher is incremental: it extracts that
single file's nodes / edges, upserts them into the existing graph
(idempotent on `uid`), and short-circuits via `file_index_state` when
the content hash hasn't changed. Typical cost: 20–100 ms per file,
fire-and-forget background. Use `cos graph-reindex --force` only after
a bulk shell move (`mv` / `cp` / `git checkout`) where the hook never
fired.

## Fail-loud failure modes

- MCP backend down → tools return `fail("unavailable", ...)` with
  `retryable=true`. Retry after `cos graph-reindex` / server restart
  — do NOT guess.
- Graph empty (fresh repo) → `_query`/`_context` return empty lists.
  Run `make docs-index` / `make task-sync` / `cos graph-reindex` first.
- Confidence below 0.3 → the edge is probably a false positive.
  `_impact` clusters these under the `context` tier so agents can
  ignore noise.

## Web UI

For visual exploration, the unified React SPA exposes the graph at
[http://127.0.0.1:9188/graph](http://127.0.0.1:9188/graph). Start it
with `cos hub start` (FastAPI + uvicorn singleton on port 9188 that
serves every registered project). The page picks a root node, runs
depth-bounded BFS, and renders with Sigma.js + Graphology — useful
when:

- An impact/rename plan returns >10 affected files and the agent (or
  user) wants to see clusters before approving.
- Walking a CONTAINS spine (Folder→File→Class→Method) is easier than
  re-issuing tool calls.
- Sharing a snapshot with a human collaborator who needs to *see* the
  blast radius rather than read JSON envelopes.

For one-off static export (no live server, embeddable HTML), the
legacy `cos graph-viz` command still works — kept intentionally for
sharing/embedding.

## Link-backs

- Phase I plan: [docs/phase-i-knowledge-graph-plan.md](../../../docs/phase-i-knowledge-graph-plan.md)
- MCP envelope: [docs/engineering/mcp-error-envelope.md](../../../docs/engineering/mcp-error-envelope.md)
- Rule 14 (envelope): [CLAUDE.md](../../../CLAUDE.md)
