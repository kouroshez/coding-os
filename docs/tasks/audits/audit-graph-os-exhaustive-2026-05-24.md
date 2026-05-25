# Audit — Graph OS Exhaustive (2026-05-24)

**Task:** TASK-029
**Status:** in_progress (findings logged, fixes deferred)
**Trigger:** user exhaustive intent (" graph", "", "", "")
**Scope:** all 17 `cos_graph_*` MCP tools + extractors + SQLite backend + reindex dispatch + envelope contract.

## Baseline snapshot

- nodes: 38607
- edges: 77018
- evidence: 39121
- pytest: **665 pass / 16 skip / 0 fail** (`uv run --extra graph_os pytest src/core/graph_os/tests/`)
- doctor: `healthy=false` (3 categories — see Cat 1-3)

## Findings — counts_before / counts_after / root cause

| # | Severity | Tool / Layer | Symptom | Count before | Root cause | Fix |
|---|---|---|---|---|---|---|
| 1 | hi | doctor | 55 orphan nodes (mostly `code:external:unresolved:*`, also `doc:file:CLAUDE.md`, etc.) | 55 | extractor emits unresolved-stub nodes that no edge references back to | filter doctor to ignore `code:external:*`; OR drop stub nodes on PostToolUse compaction |
| 2 | **CRITICAL** | resolve | uid/kind/label 3-way rotated on every FTS5 hit | 100% of fts5-strategy hits | column-order desync: [graph.py:2787](src/core/graph_os/tools/graph.py#L2787) selects `uid, kind, label` but [sqlite_backend.py:619](src/core/graph_os/backends/sqlite_backend.py#L619) `_row_to_node` reads `kind=row[0], label=row[1], uid=row[2]` | re-order SELECT to `n.kind, n.label, n.uid, …` OR change `_row_to_node` to use `sqlite3.Row` keys |
| 3 | hi | doctor | 48 self-loops (edges where source_uid==target_uid) | 48 | extractors emit self-referencing edges (e.g. `KuzuBackend.close → KuzuBackend.close`) — likely AST visitor mishandles recursion / nested call resolution | filter self-loops in extractor + run `cos_graph_doctor(fix=true)` |
| 4 | hi | doctor | 2958 stale-path nodes across 705 files | 2958 | doc indexer extracts relative paths from inside doc files (`../../STYLE_GUIDE.md`, `../../api-contracts/…`) and creates `doc:file:` nodes for paths that don't resolve | resolve relative paths against the doc's directory before emitting the uid |
| 5 | **CRITICAL** | impact | `will_break` tier filled with `contains` edges (structural parents), real consumers in `should_review` | every impact call | tier classifier ([graph.py:849-855](src/core/graph_os/tools/graph.py#L849)) is **confidence-only**: `>=0.9→will_break`, `>=0.5→should_review`. `contains` edges (conf=1.0) win regardless of semantic. `calls`/`constructs` (0.5/0.85) demoted. | gate `will_break` on edge_type ∈ {calls, imports, constructs, accesses_field, has_param_type, references_doc} — never `contains` |
| 6 | **CRITICAL** | rename_plan | class-rename returns 0 call_sites despite real consumers | 100% of class renames where users are `constructs`/`has_param_type` | hard-coded edge filter ([graph.py:1711](src/core/graph_os/tools/graph.py#L1711)) `call_edge_types = ("calls", "accesses_field", "imports")` — missing `constructs`, `has_param_type`, `inherits_from`, `dispatches`, `awaits` | extend tuple to include constructs/has_param_type/inherits_from at minimum |
| 7 | med | trace | many `code:external:unresolved:*` steps in the walk (mcp.run, logger.info, sys:exit) | per-call (15-step example: 8/15 steps were unresolved external stubs) | walk emits every outbound edge incl. unresolved external identifiers without a kind-filter | filter `code:external:*` from walk OR push them into `terminal_branches` instead of `steps` |
| 8 | med | similar | top_k=5 returned only 1 hit for major class | per-call | scorer `bge-m3+difflib-blend` thresholds at confidence_min=0.5 default — relaxes to top_k only when many candidates pass | document the threshold behaviour; consider auto-relaxing to fill top_k when fewer pass |
| 9 | **CRITICAL** | communities | response = 236KB despite `top=5` | 1 call | `cos_graph_communities` returns top=5 named processes but each process embeds 19+ full member objects → response blows past MCP token budget | hard-cap total response token estimate OR truncate `members` to a max per process (e.g. 10) when serialising |
| 10 | **CRITICAL** | centrality | top results = `unresolved:str` (3000), `pathlib:Path` (1688), `sqlite3:sqlite3` (843), `__future__` | every call | SELECT has no kind-filter — pulls in `code:external:*` and stdlib modules. Builtins (str/int/bool/len) dominate via `returns_type`/`has_param_type` edges | add default `exclude_kinds=("identifier","module" if external)`. Better — drop `code:external:*` and `code:module:<stdlib>` from input set |
| 11 | **CRITICAL** | ranking | top 10 = all stdlib (`__future__`, `pathlib`, `typing`, `logging`, …) | every call | same as #10 + ranking has no default exclude | mirror #10 fix in `cos_graph_ranking._NODE_CAP` SELECT |
| 12 | hi | ranking | `query="graph backend"` returns identical top to global | per-call | personalization ([graph.py:2386-2396](src/core/graph_os/tools/graph.py#L2386)) requires `lower_q in label.lower()` exact-substring match. "graph backend" matches no label literally → empty personalization vector → uniform teleport | use token-based match (split query on whitespace, hit any token); OR fall back to FTS5 candidate set |
| 13 | hi | entrypoints | top=10 = 10 test functions all from one file `test_agent_runtime.py` | per-call | total=4555 entrypoints; scoring ties at 0.85 for all `path_tests + label_test_prefix + uid_test`; tie-break is row-order so the alphabetically-first file wins | add deterministic tie-break on (file_path, start_line) OR diversify by file/kind within the top-N |
| 14 | **CRITICAL** | export | mermaid/dot: every method of a class collapses to identical node ID | per-call with class-context | `_safe_id` ([graph.py:2015-2016](src/core/graph_os/tools/graph.py#L2015)) `re.sub(r"[^A-Za-z0-9_]", "_", uid)[:60]` — truncates after 60 chars, so all `code:method:src/core/graph_os/backends/sqlite_backend.py::SqliteBackend.<anything>` collide | hash + short-prefix scheme (e.g. `f"{prefix[:40]}_{sha1(uid)[:8]}"`); OR len(uid) instead of 60 |
| 15 | med | path | shortest path goes through shared stdlib stubs (`__future__`, `unresolved:bool`) | per-call between unrelated functions | BFS treats all edges equally — finds 4-hop path via shared type-stub | weight edges (contains=0, imports=2, calls=1, has_param_type=10) and prefer semantic paths OR exclude `code:external:*` from BFS |
| 16 | med | contracts | lists 79 MCP tools INCLUDING removed `cos_graph` shim | 79 (should be 78 — `cos_graph` is removed) | graph node for `cos_graph` MCP tool exists at server.py:947 — registry not refreshed when tool was decommissioned | re-extract `src/core/thinking_os/server.py` after the removed-shim commit; OR add tombstone state to mcp_tool nodes |
| 17 | low | context | `cos_graph_context("cos_graph_doctor")` returns `not_found` despite fuzzy match docstring | per-call by unqualified label | resolve order in `_resolve_uid` doesn't include FTS5 — only path/prefix/`code:file:`/`doc:file:`/`folder:` variants. Fuzzy label not actually wired | wire FTS5 last-resort fallback inside `_resolve_uid` |
| 18 | low | references | file uid `code:file:server.py` has 0 inbound `imports` | structural | by design — `imports` is module→module not file→module — but `code:file:` uid is also returned by `resolve`, so an agent following the docs may pick the wrong uid | doc the asymmetry in resolve output OR auto-cast file-uid→module-uid for `imports` queries |
| 19 | low | communities | tool returns `processes` key, not `communities` | per-call | TASK-075 renamed Louvain output to "processes" but skill docstring still says "communities/clusters/subsystems" | refresh skill docstring + tool description |

## Top-priority hard-fail blockers (recommend fix before next merge)

1. **#2** — resolve column-order corruption affects every FTS5-strategy hit (massive surface area: any natural-language query returns garbled data).
2. **#5** — impact tier inversion makes the tool actively misleading for blast-radius decisions.
3. **#6** — rename plan misses constructs/has_param_type → class renames silently corrupt code.
4. **#9** — communities token-bomb blocks safe MCP invocation.
5. **#10/#11** — centrality/ranking output is dominated by stdlib noise — both tools currently useless for navigation.
6. **#14** — mermaid/dot diagram node-id collisions corrupt every exported diagram.

## Coverage statement

- All 17 `cos_graph_*` tools called at least once (smoke).
- pytest src/core/graph_os/tests/ — 665 pass.
- 19 root-caused findings with file:line citations.
- 6 marked CRITICAL; system NOT shipping-grade until those fixes land.

## Resume marker

- pytest re-run pending after fixes.
- `cos graph-reindex --force` pending (will move counts #3/#4 toward 0).
- reviewer subagent re-grep pending.

## Evidence (filed after reviewer pass)
