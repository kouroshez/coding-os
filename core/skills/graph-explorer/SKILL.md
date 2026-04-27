---
name: graph-explorer
description: Navigate the graph_os knowledge graph before editing load-bearing code. Use when tracing dependencies, planning a rename, auditing API surface, or answering "what breaks if I change this?". Pairs with codebase-explorer — graph-explorer wins for symbol-precise queries, codebase-explorer wins for conceptual code-reading.
---

# graph-explorer

Purpose: Load the Phase I graph_os toolset (`cos_graph_*` MCP tools) and
use it deliberately before any non-trivial code edit. The graph is the
third retrieval layer (CLAUDE.md Three-Layer Retrieval) — use it when
tree-grep or past-memory searches return noise.

Read when: Editing `core/**` or `cli/**`, producing a rename plan,
auditing API/MCP contracts, answering "what depends on X".

Skip when: You already know the blast radius, or the change is a
self-contained one-file edit with no callers.

## Decision ladder

1. **Need to know "what calls this?"** → `cos_graph_references(uid)`.
2. **Need surrounding context before editing?** → `cos_graph_context(uid_or_name, depth=1)` (F5 Step 1).
3. **Planning a refactor?** → `cos_graph_impact(uid, depth=3)` (F2 Step 10) groups edges by risk tier.
4. **Renaming a symbol?** → `cos_graph_rename_plan(uid, new_name)` before any `Edit` — returns call-sites, doc refs, tests, string literals.
5. **API / contract audit?** → `cos_graph_contracts(kinds=["http","mcp"])` (F4 + F9).
6. **Tracing a fault?** → `cos_graph_trace(entry_uid)` (F7 Step 2).
7. **"Is anything similar?"** → `cos_graph_similar(uid, top_k=5)`.
8. **Shortest dependency path?** → `cos_graph_path(source, target)`.
9. **Need a diagram?** → `cos_graph_export(format="mermaid", root_uid=...)`.
10. **Pre-commit self-review?** → `cos_graph_detect_changes(files=[...])` — call BEFORE `make verify`.

Every response carries `data.meta.layer="graph"` and `data.meta.backend`
so you can confirm which store answered. When `meta.backend_fallback=true`
the answer came from the SQLite fallback (lower precision on deep walks).

## Enforcement

- `enforce-graph-context.sh` — when editing a file under a path the
  hook treats as load-bearing (the matcher is built into the script —
  there is no `rag-config.yaml::graph.enforce_context_on` key today),
  the hook warns if no `.graph-context-<uid>` marker exists in
  `$COS_AGENT_DIR` for this session.
- `enforce-rename-plan.sh` — if you attempt a multi-file rename-like
  Edit without a prior `cos_graph_rename_plan` in this session, the
  hook warns + suggests the command.

Both hooks are off by default; set `COS_ENFORCE_GRAPH_CONTEXT=1` to
warn or `COS_ENFORCE_GRAPH_CONTEXT=strict` to block.

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
