# Graph-OS Deep Audit — Fix Checklist (2026-05-25)

Companion to [graph-os-deep-audit-findings-2026-05-25.md](graph-os-deep-audit-findings-2026-05-25.md). 63 defects → 5 grouped waves of atomic commits. One fix → one commit (Rule 24 commit-message contract).

**Task:** TASK-032 · **Constraint:** Rule 22 anti-overengineering — smallest correct change per defect.

## Wave 1 — Atomic line fixes (graph.py only, no semantic shift)

- [ ] **F-G2** `cos_graph_references` default `kinds` → `_BEHAVIOURAL_EDGE_TYPES` SSOT · [graph.py:1300](../../src/core/graph_os/tools/graph.py#L1300)
- [ ] **F-G3a** `kinds_csv: str = ""` for 7 tools (query, context, detect_changes, trace, references, export, contracts, resolve) — accept CSV; JSON-list fallback inside · 7 tool sigs
- [ ] **F-G4** `cos_graph_impact` default `confidence_min=0.3` (was 0.5) · [graph.py:878](../../src/core/graph_os/tools/graph.py#L878)
- [ ] **F-G5** `cos_graph_contracts` default `bucket_limit=200` (was 2000) · [graph.py:1915](../../src/core/graph_os/tools/graph.py#L1915)
- [ ] **F-G11** `cos_graph_path` walk_truncated flag — only set when frontier saturation hit · [graph.py:1396](../../src/core/graph_os/tools/graph.py#L1396)
- [ ] **F-G22** `limit≤0` → validation fail; clamp `limit>max` + `meta.limit_clamped` · references/impact/rename_plan
- [ ] **F-G27** `cos_graph_doctor` add `meta.fixable_categories=["self_loops","stale_paths"]`
- [ ] **F-G31** `cos_graph_centrality` reject `by ∉ {degree,betweenness,eigenvector}` (validation)
- [ ] **F-G34** + remove `eigenvector` from advertised list (only degree/betweenness implemented) OR implement
- [ ] **F-G35** `cos_graph_export` enforce global `max_nodes` cap + `meta.nodes_capped_at`
- [ ] **F-G38** `cos_work_log_append` accept `note` alias of `summary`
- [ ] **F-P2** `cos_graph_communities` envelope-cap: if projected tokens > 5000 reduce `max_members` adaptively + truthful `meta.truncated`

## Wave 2 — Semantic fixes (kind weighting, stdlib exclude, limit clamps)

- [ ] **F-G6** `cos_graph_centrality` default exclude `code:module:<stdlib>` set (`__future__,pathlib,sys,json,pytest,os,sqlite3,logging,...`)
- [ ] **F-G7** `cos_graph_ranking` same stdlib exclude + de-weight `code:function:tests/*`
- [ ] **F-G8** `cos_graph_resolve` weight `kind ∈ {class,function,method,interface}` > import > external; enforce `limit` strictly
- [ ] **F-G9** `cos_graph_context._resolve_uid` FTS5 fallback applies same kind preference
- [ ] **F-G15** `cos_graph_ranking` expose `meta.node_cap=5000`
- [ ] **F-G19** `cos_graph_detect_changes` risk = behavioural-edge inbound count, not contains-children
- [ ] **F-G20** `cos_graph_entrypoints` boost `kind in (cli_entry, http_route, mcp_tool, scheduled_job)` over `kind=test`
- [ ] **F-G23** `cos_graph_path` meta `frontier_edge_limit` (rename from `hop_limit`); echo `max_hops` cleanly
- [ ] **F-G29** `cos_graph_path` BFS `seen` set to dedup consecutive nodes
- [ ] **F-G32** `cos_graph_query` min query length ≥ 2 → validation
- [ ] **F-G39** same kind-weight fix in `cos_graph_query` FTS5 ranking
- [ ] **F-P5** `cos_graph_path` reduce per-hop edge cap from 1000 → 200 for 5-hop at 1M-node contract

## Wave 3 — Extractor coverage + correctness (code_python.py + siblings)

- [ ] **F-G1+G28** AST decorator extractor: walk module-level `FunctionDef.decorator_list` (currently class-method only) — emit `is_decorated_by` for module-level `@decorator def f(): ...`
- [ ] **F-G21** exclude `code:external:unresolved:*` from `cos_graph_similar` embedding pool
- [ ] **F-G30** audit embedding pool population for `code:function:src/core/thinking_os/tools/*.py`; backfill
- [ ] **F-E1** add migration v18: `deleted_at INTEGER NULL` on graph_nodes; switch `delete_node*` to UPDATE; filter queries `deleted_at IS NULL`
- [ ] **F-E2** code_python `code:import` UID drop `{imp.line}` → `code:import:<path>::<local_name>` (carry line in `start_line`)
- [ ] **F-E3** code_ts same fix for `code:import:<path>::<name>`
- [ ] **F-E4** code_python `_resolve_call` recalibrate: same-file-resolved=1.0; cross-module-resolved=0.9; unresolved=0.3
- [ ] **F-E5** emit `awaits` edge when `ast.Await(value=Call)` — confidence 0.9
- [ ] **F-E6** emit `dispatches` edge when call arg is itself a known function/method UID — confidence 0.7
- [ ] **F-E7** code_ts add `_DYNAMIC_IMPORT_RE`; emit `imports` edge conf 0.7
- [ ] **F-E8** code_yaml `_emit_registry_yaml` branch: detect `data.get("hooks")` shape, emit `cos:hook:<id>` nodes
- [ ] **F-E9** code_toml walk `project.optional-dependencies` + `dependency-groups`
- [ ] **F-E10** code_shell `_walk_regex` heredoc-aware stripping (regex MULTILINE)
- [ ] **F-E11** code_python `is_constructor_like` gate on resolved target kind `code:class:*`
- [ ] **F-E12** code_yaml restrict `_REFERENCE_KEYS` to known files (AGENTS.md, SKILL.md, stack.yaml)
- [ ] **F-E13** code_json strip block comments only after strict parse fails + only on line-starting `//` or `/*`
- [ ] **F-R2** Python extractor skip emit when call target is `ast.Dict/Set/Tuple/List/JoinedStr` subscript
- [ ] **F-R3** broaden `re_exports` detection: `from .X import *` + `__all__` assignment
- [ ] **F-R4** broaden `handles_event` detection: hook event names, `@router.subscribe`, `@bus.on`, SSE endpoints

After wave 3 → `cos graph-reindex --force` (rebuild on new extractor logic).

## Wave 4 — Backend (sqlite_backend.py + database.py)

- [ ] **F-G16** standalone `SqliteBackend(db_path=...)` call `database._apply_pragmas(self._conn)` after `sqlite3.connect`
- [ ] **F-G17** `count_edges` → `SELECT COUNT(*) FROM (SELECT DISTINCT source_id, target_id, edge_type ...)` (match `list_edges` dedupe)
- [ ] **F-G18** drop `_write_lock` from pure-SELECT methods: `get_node`, `get_nodes_bulk`, `count_nodes`, `count_edges`, `list_edges`, `sample_nodes`
- [ ] **F-G37** add `cleanup_deleted_files` sweep — periodic OR PostToolUse-on-delete; tie to `cos sync-doctor`
- [ ] **F-P6** sqlite per-thread connection (`pysqlite3-binary` w/ `SQLITE_THREADSAFE=2`) — Hub UI concurrency

## Wave 5 — Polish (P1 PageRank + edge cases + skill doc)

- [ ] **F-P1** `cos_graph_ranking` precompute `in_links` adjacency once → PageRank becomes O(E) per iteration · [graph.py:2641-2649](../../src/core/graph_os/tools/graph.py#L2641)
- [ ] **F-G13** `cos_graph_ranking` personalized fail-fallback signal `meta.reason="no candidate labels matched"`
- [ ] **F-G14** FTS5 tokenizer: `unicode61 categories='L*'` (drop porter) OR parallel trigram index
- [ ] **F-G24** `cos_graph_trace` strip externals from `branches[].fan_out`; keep only `external_targets`
- [ ] **F-G25** drop `data.processes` from `cos_graph_query` response (communities-only field)
- [ ] **F-G26** doc decision in skill: hard-delete intentional (Rule 22), tombstone via E1 migration covers historical-reference need
- [ ] **F-P3** [graph-explorer SKILL.md](../../src/core/skills/graph-explorer/SKILL.md) publish per-tool token bands (replace "~300 tok" claim)
- [ ] **F-P4** doc cold-cache cost; consider FTS5 preload at MCP startup
- [ ] **F-P7** track centrality at 100K nodes (no immediate action)

## Per-wave verification

| Wave | Test command |
|---|---|
| W1 | `uv run --extra graph_os pytest src/core/graph_os/tests/ -q` |
| W2 | same + `cos_graph_centrality/ranking/resolve/context/entrypoints` smoke |
| W3 | full reindex (`cos graph-reindex --force`) → `cos_graph_doctor` clean → matrix tests |
| W4 | matrix + 16-thread concurrency stress (`test_concurrency.py` extension) |
| W5 | bench re-run (`cos_graph_ranking` p99 < 500ms) + `make verify` full sweep |

## Commit policy

- Rule 24: title ≤100 chars, body ≤3 non-empty lines, no agent attribution.
- One fix → one commit. Title prefix: `fix(graph):` or `fix(extractor):` etc.
- After each wave: `git commit` then `git push` (trunk-based, Rule 23).
