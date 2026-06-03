---
description: Always-active rule when editing meta-repo authoring paths. Codifies the "graph before grep, graph before Read" discipline. Lists the 21 cos_graph_* tools and the structural questions that mandate each. Pairs with the graph-explorer skill which has the full decision ladder.
globs: "src/core/**/*.py,src/cli/**/*.py,src/adapters/**/*.py,src/templates/**/stack.yaml,src/core/hooks/registry.yaml"
alwaysApply: false
---

# Graph-First Rule (Meta-Stack)

Source of truth: [docs/engineering/graph-hallucination-cures.md](../../../docs/engineering/graph-hallucination-cures.md).
Decision ladder: [src/core/skills/graph-explorer/SKILL.md](../../../core/skills/graph-explorer/SKILL.md).

> **Inviolable**: When the question is *structural* — "who, where,
> what connects, what breaks, what calls" — call the graph **before**
> Read or grep. One graph envelope (~300 tok) replaces 5–10 file
> reads (5–50K tok).

## The 8 structural-question triggers

| Trigger phrase / intent | Tool |
|---|---|
| who calls / who uses / callers of / references to | `cos_graph_references(uid)` |
| rename / what would break if I rename | `cos_graph_rename_plan(uid, new_name)` |
| blast radius / what depends on / what breaks | `cos_graph_impact(uid, depth=3)` |
| API surface / all endpoints / all MCP tools | `cos_graph_contracts(kinds=[...])` |
| how does data flow from X to Y / trace | `cos_graph_trace(entry_uid)` |
| anything similar / near-duplicate / near-clone | `cos_graph_similar(uid, top_k=5)` |
| subsystems / clusters / map of | `cos_graph_communities()` |
| context around this file / surrounding | `cos_graph_context(uid_or_path, depth=1)` |

## The remaining 13 (ad-hoc)

| Need | Tool |
|---|---|
| Pre-commit blast-radius | `cos_graph_detect_changes(files=[...])` |
| Blast-radius of a git range (PR review) | `cos_graph_diff(base, head)` |
| Find symbol by name | `cos_graph_query(q, kind=...)` |
| NL/path/partial → canonical uid | `cos_graph_resolve(q)` |
| Entry-point discovery | `cos_graph_entrypoints()` |
| Hub / chokepoint nodes | `cos_graph_centrality(by="degree"|"betweenness")` |
| Importance ranking (PageRank) | `cos_graph_ranking(query=...)` |
| Circular dependencies (SCC) | `cos_graph_cycles(scope="imports"|"calls")` |
| Untested prod symbols | `cos_graph_test_gap()` |
| Dead-code candidates | `cos_graph_dead_code()` |
| Diagram export | `cos_graph_export(format="mermaid", root_uid=...)` |
| Shortest path between X and Y | `cos_graph_path(src, tgt)` |
| Graph health snapshot | `cos_graph_doctor()` |

## Coverage rule — `result_truncated` / `walk_truncated == true` is incomplete data

Every coverage-sensitive tool reports its budget state under one of
two distinct keys:

- **`data.meta.result_truncated`** — a result-set `limit` cut off rows
  (e.g. `cos_graph_references` returned 100 of 487 callers).
- **`data.meta.walk_truncated`** — a BFS hit its node cap (e.g.
  `cos_graph_impact` `visit_limit=500` reached before frontier
  exhausted).

These are distinct from `data.meta.truncated`, which the envelope
layer sets when *token-budget* trimming kicks in. **Acting on either
truncation flag = silent-incomplete-coverage bug.**

Mandatory check on every `cos_graph_references`, `cos_graph_impact`,
and `cos_graph_context` call:

```python
r = cos_graph_references(uid)              # default limit=100
if r["data"]["meta"]["result_truncated"]:
    r = cos_graph_references(uid, limit=r["data"]["total_count"])

r = cos_graph_impact(uid, depth=3)         # default visit_limit=500
if r["data"]["meta"]["walk_truncated"]:
    # raise the cap OR step down depth and walk frontier by frontier
    r = cos_graph_impact(uid, depth=3, visit_limit=5000)
```

Full workflow + per-task-class budget recipes:
[graph-explorer skill — Coverage contract](../../../core/skills/graph-explorer/SKILL.md#coverage-contract--never-trust-a-single-call-blindly).

## Hard enforcement (current)

- `enforce-skill.sh` — BLOCKS Edit on `src/core/**/*.py`, `src/cli/**/*.py`, `src/adapters/**/*.py` unless `Skill graph-explorer` was invoked in this session.
- `enforce-graph-context.sh` — WARNS (or BLOCKS in strict) on Edit of files in `.coding-os/rag-config.yaml::graph.enforce_context_on` without a prior `cos_graph_context` call.
- `enforce-rename-plan.sh` — WARNS on identifier-rename-shaped Edit without a prior `cos_graph_rename_plan`.
- `nudge-graph-os.sh` — UserPromptSubmit; pattern-matches structural questions and emits a tool recommendation.

To promote enforce-graph-context to BLOCK mode:
`export COS_ENFORCE_GRAPH_CONTEXT=strict` (per session, or in `cos-env.sh`).

## Anti-patterns (do not)

- **Skip the graph because "I already know the codebase"** — memory drifts, the graph is HEAD-of-tree truth.
- **Run grep first, graph second** — grep is a fallback for non-symbol literals (comments, error messages).
- **Read 6 files looking for callers** — `cos_graph_references` answers in one envelope.
- **Plan a rename without `cos_graph_rename_plan`** — you'll miss doc refs, fixtures, string literals.
- **Ignore `meta.backend_fallback=true`** — SQLite walks deeper but may be incomplete on dim-mismatched embeddings; rerun with Kùzu when feasible.

## When grep IS correct

- Searching for a string literal (error message, log line, comment, copy text).
- Searching inside `node_modules/`, `.venv/`, lock files (graph excludes these).
- Verifying a rename truly landed in NON-symbol locations (graph already covered the symbol-shaped ones).

The skill `search` (`src/core/skills/search/SKILL.md`) has the full grep
discipline + ground-truth-count protocol.

## Why this rule exists

The agent's biggest source of token waste and false confidence is
"reading the wrong files" or "missing call-sites a grep didn't catch."
The graph eliminates both. This rule encodes that discipline so the
agent doesn't have to rediscover it every session.
