---
description: Always-active rule when editing meta-repo authoring paths. Codifies the "graph before grep, graph before Read" discipline. Pairs with the graph-explorer skill which has the full decision ladder.
globs: "src/core/**/*.py,src/cli/**/*.py,src/adapters/**/*.py,src/templates/**/stack.yaml,src/core/hooks/registry.yaml"
alwaysApply: false
---

# Graph-First Rule (Meta-Stack)

> **Inviolable**: when the question is *structural* — who calls, what breaks, what connects, rename, trace — call the graph **before** Read or grep. `references` and `rename_plan` measure **~75–82% cheaper** than a competent grep-then-read across four repos from 36 to 3,317 files ([bench](../../../docs/engineering/third-party-token-bench.md)), and they return a `total_count` grep cannot give you.
>
> **Two measured exceptions — know them before you burn budget.** `impact(depth=3)` is size-dependent: +71–74% on large repos, but **−7% on fastapi** — a wide transitive envelope can cost more than reading, so reach for depth 3 when the codebase is big enough to make reading worse. And against bare `grep` output on a *small* repo the graph loses outright (−169% on requests); if match lines answer it, they are the right tool. Whole-graph dumps (`export`/`communities`) cost tens of thousands of tokens — deliberate use only.

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
