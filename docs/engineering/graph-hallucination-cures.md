<!-- domain:ALL | layer:engineering | ssot:true | updated:2026-05-06 -->
# Graph-OS — Hallucination Cures & Token Economics

> P: Catalogue every category of agent hallucination / blind-spot the
>    knowledge graph subsystem eliminates, mapped to the exact `cos_graph_*`
>    tool that prevents it, with token-economics rationale.
> R: Routing decisions, post-mortem analysis, deciding when graph_os is
>    cheaper than read+grep.
> S: Designing new graph extractors. See `docs/engineering/graph_os-queries.md`.
> N: [graph_os-queries.md](graph_os-queries.md), [graph-use-cases.md](graph-use-cases.md), [src/core/skills/graph-explorer/SKILL.md](../../core/skills/graph-explorer/SKILL.md)

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

The four cures called out in agent guidance (`references`, `rename_plan`,
`contracts`, `impact`) are a small slice of the surface. The full list
below is the source of truth for **why** an agent should reach for the
graph instead of grep + Read + guess.

## Decision principle

> **Read the graph before reading the file.**
> A graph query (200–500 tokens of structured output) is up to **10×
> cheaper** than reading 5–10 candidate files (5–50K tokens of raw
> source) when the question is *structural* ("who, where, what
> connects, what breaks").

Use file Read **only** for the 1–3 files the graph tells you matter.

## Hallucination → Cure matrix (17 tools)

> **Rule #0 — resolve before querying.** All `cos_graph_*` tools that accept a `uid` parameter
> require a fully-qualified UID (`code:file:<path>`, `code:function:<path>::<name>`, etc.).
> `cos_graph_context` also accepts raw paths and fuzzy labels; most others do not.
> **Always call `cos_graph_resolve(q)` first** when you don't have an exact uid.
> Raw repo paths passed directly to `cos_graph_impact` / `cos_graph_references` /
> `cos_graph_rename_plan` silently return empty results — the single highest-confidence
> hallucination pattern in this repo (agent belief score 0.93).

| # | Hallucination / blind-spot | Why it happens | Cure | Token win |
|---|---|---|---|---|
| 0 | "I'll pass a raw path to cos_graph_impact and expect results." | Tool accepts a `uid` parameter; raw paths like `src/core/foo.py` are NOT auto-resolved in most graph tools. | `cos_graph_resolve(q)` → get canonical uid → call target tool | One resolve (~100 tok) vs. repeated empty-result retries |
| 1 | "I'll grep for callers and hope the variants match." | Identifier appears as `foo`, `foo()`, `"foo"`, `foo_bar`, … | `cos_graph_references(uid)` | One call vs. 4 grep variants × Read of each hit |
| 2 | "Renaming this will only affect this file." | Doc refs, test fixtures, string literals, error messages stay invisible to grep | `cos_graph_rename_plan(uid, new_name)` | Pre-classified rename targets vs. iterative grep cycles |
| 3 | "I think this function is unused." | False — used reflectively, via decorator, or via dynamic dispatch | `cos_graph_references(uid)` returning `count=0` is the **only** authoritative dead-code signal | Avoids deleting load-bearing code (catastrophic miss) |
| 4 | "Where is this endpoint registered?" | Routes split across decorator + router + middleware | `cos_graph_contracts(kinds=["http"])` | One call vs. multi-file Read of router + apps |
| 5 | "What MCP tools exist?" | Tools registered via decorators in 12+ files | `cos_graph_contracts(kinds=["mcp"])` | Authoritative list vs. brittle grep `@mcp.tool` |
| 6 | "Which files will my change break?" | Transitive dependents invisible to grep | `cos_graph_impact(uid, depth=3)` | Risk-tiered groups vs. unbounded BFS by hand |
| 7 | "Is this similar to another helper?" | Code dedup misses near-duplicates | `cos_graph_similar(uid, top_k=5)` | Surfaces refactor candidates with similarity score |
| 8 | "How does data flow from entry X to result Y?" | Multi-hop call chain is hard to trace by reading | `cos_graph_trace(entry_uid)` or `cos_graph_path(src, tgt)` | Single ordered walk vs. recursive Read-and-grep |
| 9 | "Did anything I just changed affect graph nodes I care about?" | Diff-vs-graph mapping by hand is error-prone | `cos_graph_detect_changes(files=[...])` | Pre-commit, regen-aware blast radius |
| 10 | "Which functions are entry points (HTTP, CLI, MCP, jobs)?" | Entry points scattered across patterns | `cos_graph_entrypoints()` returns scored candidates | Prevents "no main found" planning waste |
| 11 | "What are the natural subsystems / clusters in this codebase?" | New repos look monolithic until you map them | `cos_graph_communities()` (Louvain) | Onboarding map without manual archaeology |
| 12 | "Which symbols are hubs — high blast-radius?" | High-degree nodes feel ordinary in source | `cos_graph_centrality(by="degree"|"betweenness")` | Prioritises review on actual chokepoints |
| 13 | "Which symbol matters most for this query?" | Naive top-k by name match is noisy | `cos_graph_ranking(query=...)` (PageRank, personalised) | Better than fuzzy filename match |
| 14 | "Find me anything that mentions X." | Plain grep buries you in test fixtures + docs | `cos_graph_query(q)` (label + docstring search, kind-filtered) | Filtered to structural matches |
| 15 | "Show me the surrounding context before I edit." | Read 1 file at a time, lose the connections | `cos_graph_context(uid, depth=1)` | One subgraph vs. Read of N neighbours |
| 16 | "Sketch this subsystem." | Mermaid by hand drifts from reality | `cos_graph_export(format="mermaid", root_uid=...)` | Always-fresh diagram, copy-pasteable |
| 17 | "Is the graph itself healthy / why are answers stale?" | Backend selection / extractor breakage hides | `cos_graph_doctor()` — orphans, dangling edges, duplicates | One health snapshot vs. SQL spelunking |
| 18 | "Where does this npm/pypi/crates dep come from?" | Config files (package.json / pyproject.toml / Cargo.toml / tsconfig.json / mcp.json / settings.json) were invisible to the graph before 9bee865 — agents had to read each file by hand | `cos_graph_query` now finds `npm:package:<n>`, `pypi:package:<n>`, `crates:package:<n>`, `mcp:server:<n>` directly; `cos_graph_references(uid)` traces back to the declaring config file | One graph hop vs. multi-file Read + manual JSON/TOML parse |

## Tool by intent

| Intent | First-call tool |
|---|---|
| **Resolve a name/path to a uid** | **`cos_graph_resolve`** ← start here when uid unknown |
| Find by name / label | `cos_graph_query` |
| Surrounding subgraph | `cos_graph_context` |
| Who references this | `cos_graph_references` |
| Blast radius (downstream) | `cos_graph_impact direction=downstream` |
| Blast radius (upstream) | `cos_graph_impact direction=upstream` |
| Plan a rename | `cos_graph_rename_plan` |
| Pre-commit diff impact | `cos_graph_detect_changes` |
| Forward execution walk | `cos_graph_trace` |
| Shortest connecting path | `cos_graph_path` |
| Find similar code | `cos_graph_similar` |
| API/contract surface | `cos_graph_contracts` |
| Entry-point discovery | `cos_graph_entrypoints` |
| Subsystem clusters | `cos_graph_communities` |
| Hub / chokepoint nodes | `cos_graph_centrality` |
| Importance ranking | `cos_graph_ranking` |
| Diagram export | `cos_graph_export` |
| Health snapshot | `cos_graph_doctor` |

## Token economics (concrete numbers)

| Workflow | Without graph | With graph | Saving |
|---|---|---|---|
| "Where is `cos_safe_tool` called?" | 6 grep variants × ~120 tok output + Read 4 hits @ 800 tok = **~3920 tok** | `cos_graph_references` envelope ~280 tok | **93%** |
| "Plan rename `foo` → `bar`" | Iterative: grep, edit, find missed test, grep again × 3 cycles ≈ **~6000 tok** | `cos_graph_rename_plan` returns full set in one envelope ~450 tok | **92%** |
| "Audit MCP API surface" | Read 12 register files @ 1500 tok = **~18000 tok** | `cos_graph_contracts(kinds=["mcp"])` ~700 tok | **96%** |
| "Onboard to repo / find subsystems" | Read 50 README+entry files = **~120K tok** | `cos_graph_communities` + `cos_graph_export` = ~3K tok | **97%** |
| "Pre-commit blast-radius" | git diff + manual chase = **~5–10K tok** | `cos_graph_detect_changes(files=changed_paths)` ~600 tok | **>90%** |

The five workflows above are the highest-frequency moves in any
non-trivial repo. Cumulative saving across one COMPLICATED task: **15K–
50K tok**, often the difference between fitting in context and being
forced to compact.

## Anti-patterns (do not)

- **Skip the graph because "I already know the codebase."** Memory drifts; the
  graph is HEAD-of-tree truth. Use `cos_graph_doctor` if unsure of freshness.
- **Run grep first, graph second.** Grep is a fallback for **string literals
  not in the graph** (comments, error messages). For symbols, graph is canonical.
- **Use only one tool family.** Graph for "what connects?", `cos_doc_search`
  for "what's the spec?", `cos_search` (memory) for "have I solved this?".
- **Ignore `meta.backend_fallback=true`.** SQLite walk-results are deeper but
  may be incomplete on dim-mismatched embeddings. Rerun with Kùzu when feasible.

## Hook-level enforcement

| Trigger | Hook | Behavior |
|---|---|---|
| Edit on file in `rag-config.yaml::graph.enforce_context_on` glob | `enforce-graph-context.sh` | Warn (or block in strict) until `.graph-context-<uid>` marker exists |
| Identifier-rename-shaped Edit | `enforce-rename-plan.sh` | Warn (or block) without a prior `cos_graph_rename_plan` marker |
| Empty graph at SessionStart | `warn-graph-empty.sh` | One-shot SessionStart warning |
| Bulk shell ops (mv/rm/git checkout) | `auto-reindex-shell-ops.sh` | Schedule background re-index |
| UserPromptSubmit with structural keywords | `nudge-graph-os.sh` | One-line discovery nudge with the right tool name |

## Roles that mandate graph use

The Compose-Chain dispatcher loads these roles for COMPLICATED+ tasks; each
role's allowed tool list pins specific graph tools:

| Role | Pinned graph tools |
|---|---|
| analyst | `cos_graph_query`, `cos_graph_context` |
| architect | `cos_graph_query`, `cos_graph_impact`, `cos_graph_contracts` |
| debugger | `cos_graph_trace`, `cos_graph_references`, `cos_graph_impact` |
| deployer | `cos_graph_contracts` |
| implementer | `cos_graph_references`, `cos_graph_context` |
| observer | `cos_graph_contracts` |
| refactorer | `cos_graph_similar`, `cos_graph_impact`, `cos_graph_context` |
| researcher | `cos_graph_query` |
| reviewer | `cos_graph_references`, `cos_graph_trace` |
| security_auditor | `cos_graph_contracts`, `cos_graph_references` |

Source of truth: `src/core/thinking_os/roles/*.yaml`.
