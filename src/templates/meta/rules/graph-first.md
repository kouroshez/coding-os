---
description: Always-active rule when editing meta-repo authoring paths. Codifies the "graph before grep, graph before Read" discipline. Pairs with the graph-explorer skill which has the full decision ladder.
globs: "src/core/**/*.py,src/cli/**/*.py,src/adapters/**/*.py,src/templates/**/stack.yaml,src/core/hooks/registry.yaml"
alwaysApply: false
---

# Graph-First Rule (Meta-Stack)

> **Inviolable**: when the question is *structural* — who calls, what breaks, what connects, rename, trace — call the graph **before** Read or grep. A targeted envelope (references/impact/rename of one symbol) costs a few hundred to a few thousand tokens (heuristic chars/4; measured by `make bench` → `token_cost`) and replaces grepping + reading every matching file — the saving scales with codebase size. Whole-graph dumps (`export`/`communities`) cost far more (tens of thousands of tokens); reach for them deliberately, not for a quick lookup.

| Intent | Tool |
|---|---|
| who calls / references | `cos_graph_references(uid)` |
| rename | `cos_graph_rename_plan(uid, new_name)` |
| blast radius | `cos_graph_impact(uid, depth=3)` |
| API/MCP surface | `cos_graph_contracts(kinds=[...])` |
| data-flow trace | `cos_graph_trace(entry_uid)` |
| similar / near-clone | `cos_graph_similar(uid)` |
| find by description | `cos_graph_search(query)` |
| subsystem map | `cos_graph_communities()` |
| context around file | `cos_graph_context(uid_or_path, depth=1)` |

**Coverage rule:** `meta.result_truncated` / `walk_truncated == true` ⇒ incomplete — re-query with `limit=total_count` / a higher `visit_limit`. Never act on a truncated envelope.

Grep is correct only for non-symbol literals (error strings, comments, copy) and graph-excluded dirs (`node_modules/`, `.venv/`, lock files).

The full decision ladder, per-task budgets, anti-patterns, and the other 13 tools live in `Skill graph-explorer` and [docs/engineering/graph-hallucination-cures.md](../../../docs/engineering/graph-hallucination-cures.md). Enforcement: `enforce-skill.sh` (BLOCK on core/cli/adapters .py without the skill), `enforce-graph-context.sh` + `enforce-rename-plan.sh` (warn; `COS_ENFORCE_GRAPH_CONTEXT=strict` to block).
