<!-- domain:META | layer:engineering | ssot:false | updated:2026-05-27 -->
# Graph-OS Round 3 Audit Findings (2026-05-26)

Companion to [docs/tasks/audits/audit-graph-os-deep-2026-05-25.md](../tasks/audits/audit-graph-os-deep-2026-05-25.md). Full Round 3 defect register; pointer kept under the 3K-token lint cap.

**Task:** TASK-037
**Trigger:** user exhaustive intent — " graph ", "", "", "", "".
**Scope:** what TASK-029/032/033 did NOT cover — deep-walk stress (depth 3-5), envelope honesty across ALL 17 tools at default + extreme args, extractor coverage gaps post-fix, concurrency + reindex safety under P6 thread-local conns, persona end-to-end cross-tool agreement.
**Methodology:** 5 parallel diagnostic subagents (deep-traversal, extractor-parity, envelope-budget, concurrency-stress, persona-flow) + reviewer subagent re-grep. All probes against live `.coding-os/coding-os.db` (37 617 nodes / 76 285 edges raw / 75 581 deduped).
**Prior:** TASK-032 audit catalogued 63 defects (G1-G39, E1-E13, P1-P7, R1-R4); most landed via 14+ commits.

## Baseline snapshot (2026-05-26 pre-round-3)

- nodes: 37 617 · edges raw 76 285 / deduped 75 581 (G17 working) · evidence 40 498
- doctor `healthy=false` — 1 061 orphans (mostly `code:external:unresolved:*`) + 386 stale_paths (regression of F13 surface)
- pytest `src/core/graph_os/tests/`: **686 pass / 16 skip / 0 fail** in 17.25 s
- 4× tree-sitter-go grammar skips (Go extractor AST-driven path not installed)

## Cross-cutting root causes (fix these first to collapse many defects)

1. **Envelope shrinker only walks `data.results`** — list-bearing buckets in `impact.tiers`, `contracts.{http_routes,mcp_tools,event_handlers}`, `export.{nodes,edges}`, `communities.processes[*].members`, mermaid `diagram` (single string) all degrade pathologically: scalar `impacted_count: int` stringified to `"[truncated…]"`, mermaid `diagram` replaced by sentinel, export delivers 0 nodes to fit edges. **G5 was patched at the symptom, not at root.** → re-open + rewrite `_shared.py::_shrink_to_budget` as per-tool strategy table. Collapses **B1 / B2 / B4 / B5 / B10 / T4 / F7**.

2. **Decorator + builtin type resolver leaks to external stubs** — `@safe_tool` decorator targets `code:external:tools._shared:safe_tool` instead of internal uid (73 edges); `has_param_type` 43% (1 860/4 346) point at `unresolved:str/int/bool/dict`; `inherits_from` 17 edges into `unresolved:RuntimeError/Enum`. **Pre-seed `BUILTIN_TYPE_UIDS` + post-process decorator targets against in-repo import map.** Collapses **X1 / X6 / X8** (the actual root cause behind G1's 95% miss claim).

3. **Markdown link extractor regex over-captures** — backtick prose fragments like `` `docs/playbooks` `` are emitted as `doc_file` nodes. Root cause of 386 stale_paths regression + ranking pollution. **Replace regex with commonmark/mistune inline-link AST.** Collapses **X7 / G37 residual / part of B13**.

4. **Silent param overrides on coverage tools** — `cos_graph_context(depth=2..4)` returns byte-identical responses (TASK-036 SUMMARY mode is depth-agnostic; depth silently ignored); `cos_graph_centrality(top=50)→49`; `cos_graph_communities(top=50,members=20)→33×1`; `cos_graph_export(max_nodes=500)→0`; `cos_graph_trace(entry=server.py::main)` auto-resolves to *different file* with `start_source="explicit"`. **Make silent overrides loud** — fail validation OR emit `meta.requested_X` + `meta.delivered_X` + `meta.reason`. Collapses **T3 / B6 / B9 / B10 / B12 / F8**.

5. **Cross-tool answer disagreement is unflagged** — for "SqliteBackend callers": `rename_plan=28` / `references=28` / `impact.will_break=78 (depth=3 transitive)` / `git grep=94 across 28 files`. For "sqlite_backend.py risk": `impact=78 transitive` vs `detect_changes=low + 0 downstream`. Tools answer DIFFERENT questions but use overlapping vocabulary; agent cannot tell. **Add `meta.semantic_scope: "direct"|"transitive_depth_N"|"file_contains_only"` to every coverage tool.** Collapses **F1 / F4 / F6 / B15** at the surface level.

## Defect register

### Deep-traversal stress (Agent A — T-series, 12 defects)

| ID | Sev | Tool | Symptom | Measured | Root cause | Fix |
|---|---|---|---|---|---|---|
| T1 | HIGH | path | Paths hijack via stub hubs (`unresolved:str` has **3 083 in-edges**) producing meaningless bridges between unrelated nodes | cli/init → upsert_node "connects" via `json:dumps` (2 hops) | BFS treats stubs as ordinary nodes | Exclude `code:external:*` from intermediate hops; add `exclude_kinds` arg default `["external"]` |
| T2 | HIGH | path | Edge direction not honored — returned edge can be reverse (target→source) yet listed as forward step | server.main path edge[2] `_tree_sitter_imports_active --returns_type--> bool` printed mid-path forward | Undirected BFS adjacency, emit in stored direction | Tag each edge `traversal_direction: forward\|reverse`, restrict to directed walk |
| T3 | HIGH | context | depth=2,3,4 return **byte-identical** responses for safe_tool (same edge_count=61, same SHA) | 3 calls each ~4 350 chars identical | TASK-036 SUMMARY mode depth-agnostic | Honor depth + aggregate, or reject depth>2 with validation error |
| T4 | HIGH | impact | Envelope blown WITHOUT `truncated=true` at extreme size; depth=5 SqliteBackend = **75 232 chars**; `impacted_count: int` overwritten with `"[truncated: field exceeded envelope budget]"` (type contract broken) | will_break=90 ctx=75 nodes 75KB | No early-exit on tier-list growth; whole-field stringification | Budget-check before serialise; never stringify non-string typed fields |
| T5 | MEDIUM | impact | safe_tool depth=3..5 returns ONLY folder contains-spine ancestors (`folder:src/core/thinking_os/tools` etc.) as "downstream"; 60+ real decorator-call-sites invisible | depth=3:4, depth=4:5, depth=5:6 — all `contains` going UP the spine | Walker follows `contains` reverse, surfaces parent folders | Exclude `contains` from downstream impact; include `is_decorated_by` reverse + `calls` reverse |
| T6 | MEDIUM | path | `hops` field disagrees with edge count; `frontier_saturated=true` paired with `walk_truncated=false` is contradictory | hops=2 with max_hops=12, found via stub bridge | Stub bridge short-circuits BFS | T1 fix collapses this; expose `intermediate_external_count` |
| T7 | MEDIUM | data layer | **7× duplicate `contains` edges** per folder pair (one row per extractor: code_json, code_python, code_shell, code_ts, code_yaml, contracts, md_links); UNIQUE key includes `extractor` so dedup permits it | `SELECT COUNT(*) FROM graph_edges_v12 WHERE source_id=22 AND target_id=501032` = 7 | Each language extractor independently emits folder spine | Drop `extractor` from UNIQUE key for `edge_type='contains'` between folder/file nodes; OR emit spine from ONE designated extractor only |
| T8 | MEDIUM | resolve | `"src/cli/main.py main"` returns `code:module:cli.mcp_start` (path_resolve, conf=1.0); misses actual `src/cli/main.py::main` symbol | 1 result wrong file conf=1.0 | path_resolve picks first prefix-match on `cli.m*`, exits before FTS5 fallback | Fall through to FTS5 when path_resolve hits 1 result with low query overlap |
| T9 | LOW | context | `calls` array prints same `safe_tool.wrapper` uid 4× consecutively in summary (multi-edge dedup missing) | edge_counts.calls=4 → 4 identical wrapper rows | Summary projects edges 1-to-1 without uid-collapse | Dedup `top_edges_by_type[*]` by uid + add `count` field |
| T10 | LOW | centrality | Betweenness `kind=""` mixes module/file/doc/folder/function in top 20; folder-spine inflation makes folders dominate | top 20 = mix incl. `00-index.md` rank 3 | Computed over entire graph including doc/folder nodes | Compute on code-only subgraph by default; honor `kind` filter |
| T11 | LOW | communities | `max_members=10` requested, silently downshifted to 2 with `members_truncated=true` but no reason | 200 latent, 20 returned × 2 members | Budget-fit shrinker quiet about why | Surface `members_downshifted_because: "tokens_budget"` |
| T12 | LOW | tokens_estimated | Estimate consistent ~4 char/tok (honest per-token); BUT real bug is `truncated=false` while payload exceeds MCP cap | impact 75 232 chars / 17 352 tok = 4.3× ratio (honest) but MCP cap busted | No envelope-cap cross-check | Compare `estimated_tokens > envelope_cap` before return; set truncated + trim |

**Verifications PASS (Agent A):** trace terminates at max_steps=300; centrality(by=degree) matches SQL cross-check exactly; impact monotonic node growth at depth 3→5; path returns clean `not_found` when uid absent; no duplicate consecutive uids in paths (G29 holds); summary_mode fires correctly with `drill_hint` at depth≥2 (TASK-036).

### Extractor parity (Agent B — X-series, 12 defects)

| ID | Sev | Extractor | Symptom | Measured | Root cause | Fix |
|---|---|---|---|---|---|---|
| X1 | **REFUTED** | Python decorator | Original claim: `@safe_tool` resolves to `code:external:tools._shared:safe_tool` external stub. Reviewer SQL: **0 in-edges** to that uid with `is_decorated_by`. Either edge_type differs or uid never existed. Investigate further before fix | 0 edges (reviewer) vs Agent B's claimed 73 | Possibly already-fixed (commit 09edc67 G1+G28) but unverified — Agent B may have miscounted | Re-grep with `cos_graph_references(safe_tool, kinds=is_decorated_by)` then SQL cross-check before any extractor change |
| X2 | HIGH | TOML | `pyproject.toml::[project].dependencies` + `[project.optional-dependencies]` (118 entries) emit ZERO dep nodes | `kind=dependency` doesn't exist | Walker parses `[project.scripts]` + `[tool]` but skips array nodes | Add array-walker; emit `pypi:package:<name>` + `requires` edges |
| X9 | HIGH | JSON | `package.json` captures all 13 npm scripts but ZERO of 43 deps/devDeps | 14 nodes vs 43 deps untouched | Walker handles scripts only | Mirror X2 fix; `npm:package:<name>` + `requires` edges |
| X7 | HIGH | Markdown links | Inline backticks (`` `../architecture/adr/` ``, prose fragments) extracted as `doc_file` nodes; root cause of 386 stale_paths regression | 9 `doc_file` nodes with `../` paths + many garbage-prose labels | Regex captures any backticked string ending in `/` or `.md`, not the proper inline-link `[text]\(path\)` shape | Replace with commonmark inline-link AST; tighten to `\[[^\]]*\]\((?P<href>[^)]+)\)` |
| X8 | MEDIUM | Python type resolver | 43% of `has_param_type` edges → `unresolved:str/int/bool/dict/float`; builtins not pre-seeded | 1 860/4 346 = 43% builtin-unresolved | Resolver lacks shortcut table | Pre-seed `BUILTIN_TYPE_UIDS = {"str": "code:external:builtins:str", …}` |
| X6 | MEDIUM | Python inheritance | `inherits_from` → `unresolved:RuntimeError/str/Enum` | 17 edges target unresolved | Same root as X8 | Same builtin-seed fix |
| X5 | MEDIUM | Python variable | `kind='variable'` captures dataclass FIELDS not module-level constants — 611 noise variable nodes in `src/core/` | spot-check 15 → all dataclass fields, 0 constants | Visitor treats class-body `AnnAssign` same as module-body | Gate on visitor depth (only emit at module scope) OR add new kind `field` |
| X10 | LOW | Hook contracts | `handles_tool` edge is self-referential `module:X.sh → cos:hook:X` — semantic should be hook handles TOOL it intercepts | 128 self-referential edges | Conflates "declares hook" with "handles tool" | Rename to `declares` (exists); emit real `handles_tool` from `matcher: Edit\|Write` in registry.yaml |
| X3 | LOW | Markdown reindexer | 1 061 orphans + 386 stale_paths; many are root-relative doc paths that DO exist but aren't linked into spine | doctor sample | After F13, root-level docs sometimes lack inbound CONTAINS edge | Always emit `CONTAINS(folder:<parent>, doc:file:<self>)` |
| X11 | LOW | TOML coverage | 5× `.codex/config.toml` files exist; only `pyproject.toml` got nodes | dotfile blanket-skip filter | path-filter excludes `.codex/` | Whitelist `.codex/config.toml`; or rely on `.gitignore` instead of dot-prefix skip |
| X12 | INFO | Python awaits (E5 partial) | Only 36 `awaits` edges vs 122+ `async def` in `src/core/`; method-chain awaits silently skip when target unresolved | 36 total | Walker bails on `await self._conn.execute(...)` | Emit fallback `awaits → code:external:unresolved:<expr>` so coverage visible |

**Verifications PASS (Agent B):** E8 hook registry first-class (87 hook nodes, 76 declares edges); E10 shell tree-sitter heredoc (session-context.sh emits exactly 2 nested funcs, no heredoc false-positives); TS imports 8/8 spot-checked; in-repo inheritance resolves correctly.

### Envelope budget honesty (Agent C — B-series, 17 defects)

| ID | Sev | Tool | Symptom | Root cause | Fix |
|---|---|---|---|---|---|
| B1 | HIGH | impact | Shrinker only walks `data.results`; `tiers.{will_break,should_review,context}` bypass it; scalars stringified | Shrinker blind to tier-shape buckets | Generalize: bucket-aware list-clip; NEVER stringify non-string fields |
| B2 | HIGH | contracts | Default returns **108 729 chars** (G5 not actually fixed); `http_routes/mcp_tools/event_handlers` buckets unknown to trimmer | Same as B1 | Re-open G5; bucket-aware shrink |
| B3 | MEDIUM | contracts | Extractor walks docstring-embedded `@mcp.tool(name="cos_example", …)` and registers as real handler | Walks decorators inside string literals | Skip decorators inside docstring AST node |
| B4 | HIGH | export | `max_nodes=500` honored at fetch but post-fetch trim → **0 nodes / 0 edges delivered as 16K edges-only payload** | Shrink-edges-after-nodes ordering wrong | Shrink edges first; never deliver `nodes:[]` if `max_nodes>0`; prefer `fail("validation","reduce max_nodes")` |
| B5 | HIGH | export | Mermaid `diagram` is a single string; truncator replaces with sentinel `"[truncated…]"` — unusable payload | Same shrinker blind-spot | Cut to valid Mermaid prefix (header + N edges) OR fail validation |
| B6 | LOW | centrality | `top=50` → 49 (off-by-one tie handling) | LIMIT/SQL slice mismatch | Verify LIMIT alignment |
| B7 | MEDIUM | ranking | Global PageRank dominated by test fixtures (`tests/test_branch_guard.py::_run` etc.); high in-degree from many test methods | No noise_kinds filter post-G7 | Add `noise_kinds` filter (skip `tests/`); expose `include_tests=False` |
| B8 | MEDIUM | similar | bge-m3+difflib on decorator `safe_tool` returns 10 unrelated test functions; label-only embedding | Semantic embedding ignores docstring/body | Include docstring + body in embedding; weight by kind=function |
| B9 | LOW | communities | `max_members=5 → 4` silent shave; honest in meta but degrades data | min(requested, fit_budget) rounded down | Emit `under_delivered=true` per process |
| B10 | HIGH | communities | `top=50,members=20` → 33 communities × 1 member (members=1 kills concept) | Single-pass budget shrink chops members below floor | Two-pass: distribute fairly; never shrink members below 3 — drop tail communities |
| B11 | MEDIUM | path | Path includes backward edges + zigzags through `_shared`; misleads | Undirected BFS + no edge-kind preference | Direction-respect; prefer `calls`/`imports` over `contains`; add `edge_kinds` filter |
| B12 | **REFUTED** | trace | Reviewer re-call: `start_source="explicit"`, resolved uid = exact input `code:function:src/core/thinking_os/server.py::main`. No file-jump observed. Agent C's original probe may have used a different input form (path vs uid) | reviewer: clean resolve | Original claim wrong; close as REFUTED | n/a |
| B13 | MEDIUM | doctor | 1 061 orphans include resolvable names (`unresolved:SqliteBackend`); extractor emits unresolved stubs without retry-linking | No post-extraction sweep | Post-extract sweep: link `unresolved:NAME` → `code:class:*::NAME` when unique |
| B14 | LOW | entrypoints | `diversify=true` returns mostly `cli/` + `hooks/_helpers/` main funcs; not diverse | Tie-break doesn't actually spread across dirs | Group by top-2 path components, round-robin sample |
| B15 | HIGH | detect_changes | Touching `graph.py` + `sqlite_backend.py` yields only `contains`/`links_to` self-edges; `analyze_downstream=true` silently ignored | symbols query returns CONTAINS-edges TO file, not OUT-edges | Walk uid `code:file:<path>` AND every contained `code:class/function:` for downstream |
| B16 | MEDIUM | context | `include_content=true` on safe_tool (line 304 def, line 344 actual) returns source from `validate_enum` (~line 290) instead of safe_tool body | Off-by-N in content-extract slice | Verify node's start_line/end_line; read those bytes from file directly |
| B17 | LOW | contracts events | `cos:route:event:ts_emitter:window:keydown` returned twice with identical uid, different source files | Dedup missing per-uid OR uid not differentiated by file_path | Either dedup or differentiate uid |

**Cross-cutting summary (Agent C):** rewrite `_shared.py::_shrink_to_budget` as registered-strategy table per tool — knowledge of which fields are clipable lists vs preserved scalars vs single-blob strings. Single fix collapses B1/B2/B4/B5/B10.

### Concurrency + reindex (Agent D — C-series, 3 defects)

| ID | Sev | Layer | Symptom | Measured | Root cause | Fix |
|---|---|---|---|---|---|---|
| C1 | MEDIUM | sqlite_backend `_get_read_conn` | Read-pool ignores `_apply_pragmas` SSOT (G16 partial regression); thread-local read conns run with 32× smaller page cache + 0 mmap | read-conn `cache_size=-2000` (2MB vs 64MB primary), `mmap_size=0` (vs 256MB), `temp_store=0` (vs MEMORY), `synchronous=2` (FULL — wasted on read-only) | `_get_read_conn` opens conn + inline 4-pragma block, never calls `db._apply_pragmas` | After opening read conn, call `_apply_pragmas(conn)` then `PRAGMA query_only=ON` — one line |
| C2 | LOW | sqlite_backend `__init__` | `busy_timeout=30000` explicitly set then immediately overwritten to 5000 by `_apply_pragmas` (dead code) | live primary `busy_timeout=5000`; comment claims 30000 | G16 SSOT promotion didn't reconcile constructor pre-set vs SSOT default | Either bump SSOT default to 30000 OR move constructor set AFTER `_apply_pragmas` |
| C3 | LOW | sqlite_backend `_all_read_conns` | List grows monotonically across thread lifetimes; bounded in uvicorn (~32 threads) but unbounded under ad-hoc ThreadPoolExecutor | observed bounded today | Strong reference keeps dead-thread conns alive | Switch to `WeakValueDictionary` OR drop from list on thread GC |

**Verifications PASS (Agent D):** P6 thread-local conn pool live + delivers 1.74× speedup at 32-thread (>1.5× target); 5s × 8-thread stress = 828 ops/s 0 errors; 16-thread × 100 upserts on tmp DB = 1600/1600 ok 0 deadlocks; FTS5 sync exact (37 617=37 617); G17 dedupe 76 285 raw vs 75 581 distinct (working); no runaway background indexer.

### Persona end-to-end + cross-tool agreement (Agent E — F-series, 14 defects)

| ID | Sev | Tool | Symptom | Measured | Root cause | Fix |
|---|---|---|---|---|---|---|
| F1 | HIGH | rename_plan vs impact | rename_plan=28 call_sites, impact.will_break=78 (depth=3 transitive). Neither envelope flags the disagreement; agent cannot reconcile | 28 vs 78 (179% delta) | impact walks transitive + non-call edges; rename_plan direct only | Add `direct_only: bool` flag to impact; cross-link to rename_plan |
| F2 | HIGH | rename_plan | `test_references=[]` while 22 of 28 call_sites ARE in `tests/` dirs | 22 mis-bucketed | Routes by edge_type, not source file path | Route by `source_uid` path prefix `tests/` or `*/tests/*` → test_references bucket |
| F3 | **HIGH** (downgraded — see N2) | rename_plan | Reviewer corrected: imports ARE included BUT encoded as `edge_type=calls` in the graph (extractor conflates `from … import X` with `calls`). rename_plan returns 34 call_sites vs 23 import-files via grep; imports folded as `calls`. Bucket label lies | 34 call_sites includes import-edges mis-typed as calls | Upstream extractor encodes imports as `calls`; rename_plan accepts | Split bucket: walk `imports` edge_type for `import_sites`, `calls` for `call_sites`; FIX UPSTREAM extractor so import statements emit `imports` edge not `calls`. See N2 |
| F4 | HIGH | context vs trace | depth=2 context says `edge_counts.calls=54`, trace fan_out direct says 10. No labels saying which is transitive | 54 vs 10 | context.depth=2 transitive vs trace local; no semantic label | Rename to `transitive_edge_counts` at depth≥2 OR expose `direct_calls` |
| F5 | MEDIUM | context | `top_edges_by_type` returns DUPLICATE entries (same uid+label twice) | `_backend` ×2, `_lexical_search` ×2 | SQL lacks DISTINCT, or symbol has multiple `has_param_type` edges | DISTINCT on (uid, edge_type) OR expose `count` per uid |
| F6 | CRITICAL | detect_changes | `analyze_downstream=true` returned 0 downstream tasks + `risk_level: "low"` for file with 78 transitive callers (sqlite_backend.py) | symbols=4 self-contains, risk=low | Symbols query returns CONTAINS-edges TO file, not OUT-edges (matches B15 root cause) | Walk file uid AND every contained symbol for downstream; risk inherited |
| F7 | HIGH | impact envelope | Scalar fields `impacted_count` (int) and `direction` (str) truncated as `"[truncated: field exceeded envelope budget]"` — caller cannot tell direction queried | Hit on first depth=3 call | Shrinker truncates scalars instead of dropping array tail first (matches T4/B1) | Shrinker policy: never truncate fields `len(value)<200`; prioritize trimming `tiers.*[]` |
| F8 | HIGH | similar | Returns 10 unrelated `test_doctor.py` test functions for `cos_graph_doctor` — 0 sibling `cos_graph_*` tools surfaced | top 10 = 100% noise | Scorer matches lexical "doctor" not structural "cos_graph_*" (matches B8) | Boost same-file/folder + same-kind; demote tests when source is non-test |
| F9 | MEDIUM | similar | `total_count=200, result_truncated=true` but envelope `meta.truncated=false` — inconsistent labels | Observed | result_truncated and meta.truncated are different concepts both in meta | Rename `result_truncated`→`results_clamped` |
| F10 | MEDIUM | communities | Top-20 communities are test-flow clusters (`test_X → impl → test_Y`), not subsystems | 20/20 top communities seeded by a test function | Louvain on full edge graph; test→impl edges dominate fan | Filter test paths before Louvain OR two separate community sets (test vs prod) |
| F11 | MEDIUM | centrality | cos_graph_doctor absent from top-20 functions despite being MCP entrypoint; `cos_graph_ranking`/`cos_graph_centrality` appear (high out_degree) | doctor in_degree probably <2 | Degree centrality rewards big switch statements not "importance" | Add `mcp_tool=true` boost OR expose `weighted_centrality` by kind |
| F12 | LOW | trace | `external_targets` includes 30+ Python builtins (`str`, `int`, `range`, `isinstance`, `sorted`, `filter`) | 77 externals, ~40 builtins | F9 cure didn't include builtin allowlist | Hardcode builtin allowlist in extractor, drop pre-emit |
| F13 | LOW | rename_plan | `call_sites_total_count=29` but `call_sites` array=28; one entry is `has_param_type` not `calls` | mixed-semantic single array | Joins multiple edge_types into call_sites without typing | Split into `call_sites` + `type_references` buckets |
| F14 | INFO | resolve | Resolving `SqliteBackend` returns unrelated `_make_backend`, `_dump_projection`, `test_backend_round_trip` — fuzzy fallback too aggressive | 5 hits, 2 actually about SqliteBackend | FTS5 token match on "backend" substring | Score boost for exact-label match; demote substring-only |

### Reviewer-surfaced new defects (N-series, 4 defects)

| ID | Sev | Layer | Symptom | Measured | Root cause | Fix |
|---|---|---|---|---|---|---|
| N1 | HIGH | impact (file-level) | `cos_graph_impact` on FILE uid puts spine into `context` tier and reports `will_break: []` even when the file contains a class with 55 will_break edges; file-level impact analysis is BROKEN — doesn't aggregate child-symbol breakage | `impact(code:file:sqlite_backend.py, d=3)` → will_break=0; `impact(code:class:…SqliteBackend, d=3)` → will_break=55 | Walker queries direct file-uid neighbors only; doesn't walk contained class/function symbols | Aggregate child-symbol breakage UP to file uid OR document file-uid is a no-op and require symbol uid |
| N2 | HIGH | extractor (Python) | Graph encodes `from … import X` statements as `edge_type=calls` upstream. Confirmed by reviewer at `cli/graph_commands.py::_open_backend` line 78. Downstream effect: rename_plan call_sites bucket contaminated with import edges; impact tier picks them as `calls`; semantic of `calls` edge no longer trustworthy | `cli/graph_commands.py:78 = "from … import SqliteBackend"` emits `code:function:…_open_backend --calls--> SqliteBackend` | Python AST extractor `visit_ImportFrom` emits `calls` instead of `imports` | Emit `imports` edge for `ImportFrom` nodes; never `calls` |
| N3 | LOW | sqlite_backend pragmas | Read-pool `busy_timeout=30000` vs write-conn `5000` is a 6× divergence; if intentional needs comment, otherwise config drift | reviewer probe | C2-related: SSOT promotion inconsistent | Reconcile or comment |
| N4 | MEDIUM | context (BFS budget) | `visit_limit=50` identical at depth 2/3/4 — BFS budget never expands with requested depth, so deeper traversals silently impossible regardless of SUMMARY shape | T3 reviewer follow-up | TASK-036 SUMMARY cap budget-agnostic | Expand `visit_limit` proportional to depth OR document hard cap of 50 visits |

## Reviewer verdict tally (12 critical claims re-verified)

- **CONFIRMED 8**: T1 (3 137 in-edges vs 3 083 claim), T3 (depth byte-identical), T4 (53 642 bytes + `impacted_count:str`), X2 (0 dep nodes vs 23 grep), X7 (10 garbage uids confirmed), F6 (file=low vs class=55 contradiction), B1/B2 (116 640 bytes contracts), C1 (4 missing pragmas in read pool)
- **PARTIAL 2**: T7 (only 2 rows with c=7, not "per folder pair" — narrower scope), F3 (real defect but mis-diagnosis — imports ARE present but as `calls` — see N2)
- **REFUTED 2**: X1 (0 edges found, claim wrong as stated), B12 (trace did not jump file — exact resolve)
- **4 NEW defects surfaced**: N1 file-level impact broken, N2 imports encoded as calls upstream (highest-impact new finding), N3 read/write busy_timeout drift, N4 visit_limit doesn't scale with depth

## Cross-tool disagreement summary (the gold finding)

| Question | rename_plan | references | impact | detect_changes | git grep | Truth |
|---|---|---|---|---|---|---|
| SqliteBackend callers | 28 direct | 28 direct | 78 transitive (depth=3) | n/a | 28 files / 94 lines | Definitions differ — but **tool disagreement is silent** |
| cos_graph_query callees | n/a | n/a | n/a | n/a | n/a | context=54 transitive, trace=10 direct (**unlabeled**) |
| sqlite_backend.py risk | n/a | n/a | HIGH (78 will_break) | LOW (0 downstream) | n/a | **direct contradiction between two tools answering same Q** |

## Round 3 totals (post-reviewer)

- **60 total defects post-reviewer**: T1-T12 (12) · X1-X12 (12, X1 REFUTED → 11 active) · B1-B17 (17, B12 REFUTED → 16 active) · C1-C3 (3) · F1-F14 (14) · N1-N4 (4)
- **Active: 58** (2 REFUTED, 2 PARTIAL with corrected scope, 4 newly surfaced by reviewer)
- Severity split post-correction: **1 CRITICAL** (F6 — F3 downgraded to HIGH; X1 REFUTED) · **20 HIGH** (incl. N1, N2) · **18 MEDIUM** (incl. N4) · **19 LOW/INFO** (incl. N3)
- **5 cross-cutting root causes** that collapse 25+ surface defects (see § Cross-cutting at top)
- **Highest-impact new finding (reviewer N2):** Python AST extractor encodes `from … import X` as `edge_type=calls` upstream — corrupts the semantic of every `calls` edge in the graph and contaminates rename_plan/impact/references downstream

## Verifications PASS (Round 3) — work confirmed live

- P6 thread-local read conns deliver 1.74× speedup (>1.5× target); 0 lock errors under 32-thread stress
- TASK-036 `cos_graph_context` SUMMARY mode at depth≥2 + `drill_hint` present
- G17 count_edges DISTINCT dedupe correct (76 285 raw → 75 581 distinct, 704 dup rows surfaced)
- G29 path no-duplicate-consecutive-uids invariant still holds
- G21 cos_graph_similar excludes external/unresolved orphans
- G31/G36 centrality validation rejects bogus metric with `validation` envelope
- G32 query rejects q<2 chars
- G14 Persian FTS5 works for body content
- E8 hook registry first-class nodes (87 nodes, 76 declares edges)
- E10 shell heredoc-aware extraction (no false-positive functions inside heredocs)
- pytest matrix: 686 pass / 16 skip / 0 fail
- No background indexer runaway; no memory leak in 5-min reader stress

## Coverage statement (Round 3)

- 17/17 `cos_graph_*` tools exercised at default + extreme args (~110 distinct probes)
- Every tool measured for literal-char-count vs `meta.tokens_estimated` honesty
- 32-thread concurrent reader stress + 16-thread concurrent writer stress + reindex-while-query
- 6 PRAGMAs verified live on primary AND on read pool (gap surfaced — C1)
- All 4 persona flows simulated end-to-end with cross-tool numeric verification
- 5 parallel diagnostic subagents + reviewer subagent pending

## Suggested commit waves (Round 3 deltas — apply after reviewer PASS)

1. **W6 cross-cutting envelope shrinker** — rewrite `_shared.py::_shrink_to_budget` as per-tool strategy table. Collapses B1/B2/B4/B5/B10/T4/F7.
2. **W7 cross-tool semantic labels** — add `meta.semantic_scope` to every coverage tool; surface direct vs transitive disagreement. Collapses F1/F4/F6/B15.
3. **W8 resolver bullseye** — pre-seed builtin TYPE_UIDS + post-process decorator targets; tighten markdown link regex to commonmark AST. Collapses X1/X6/X7/X8/B13.
4. **W9 silent-override loudness** — fail validation OR `meta.requested_X`/`meta.delivered_X`/`meta.reason` for every tool that shrinks user params. Collapses T3/B6/B9/B10/B12/F8.
5. **W10 rename_plan completeness** — add `imports` edge + bucket `import_sites`; route tests to `test_references`. Collapses F2/F3/F13.
6. **W11 concurrency parity** — read-pool `_apply_pragmas`; reconcile busy_timeout 30000/5000. Collapses C1/C2.
7. **W12 polish** — T7/T9/T10/T11/X10/X11/X12/F5/F9/F10/F11/F12/F14/B3/B6/B14/B16/B17/C3.

## See also

- [audit-graph-os-deep-2026-05-25.md](../tasks/audits/audit-graph-os-deep-2026-05-25.md) — pointer doc.
- [graph-os-deep-audit-findings-2026-05-25.md](graph-os-deep-audit-findings-2026-05-25.md) — Round 2 register (63 defects, mostly fixed).
- [graph-os-deep-audit-fix-checklist-2026-05-25.md](graph-os-deep-audit-fix-checklist-2026-05-25.md) — what landed.
- [mcp-error-envelope.md](mcp-error-envelope.md) — envelope contract (B1/B2 violate).
- [graph-explorer skill](../../src/core/skills/graph-explorer/SKILL.md) — coverage / truncation discipline.
