<!-- domain:META | layer:checklist | ssot:false | updated:2026-05-28 -->
# Graph-OS Round 3 Fix Checklist (2026-05-26)

Companion to [graph-os-round3-audit-findings-2026-05-26.md](graph-os-round3-audit-findings-2026-05-26.md). Each defect triaged against Rule 22 (anti-overengineering) → KEEP / MERGE / DROP. One fix → one commit (Rule 24). Apply top-down.

## Anti-overengineering triage

**Drop principle:** if fix introduces abstraction/flag/migration for a hypothetical or rare case, drop. If three independent reports converge on same root cause → merge into one fix. If symptom is loud but blast-radius is 1 file/1 caller → low priority polish.

**Refuted by reviewer (drop):** X1 (0 edges, original claim invalid), B12 (trace resolved correctly).

## Checklist (priority order, top-down)

### W6.1 — N2 [HIGH, root-cause] Python AST emit `imports` edge for `ImportFrom`
- **Problem**: `from X import Y` emitted as `edge_type=calls` upstream → corrupts every `calls` edge semantic; contaminates rename_plan/impact/references.
- **Verdict**: **KEEP** — load-bearing. Collapses F3 (imports missing from rename_plan), N2, downstream contamination.
- **Diff size**: ~10 lines `code_python.py::_walk_imports` or visit_ImportFrom.
- **Risk**: changes confidence ratios; may break tests asserting calls count. Add regression test for known import sites.
- [ ] Patch extractor · [ ] reindex · [ ] verify pytest · [ ] commit

### W6.2 — T4/B1/B2/F7 [HIGH, root-cause] Envelope shrinker bucket-aware
- **Problem**: `_apply_token_budget` only walks `data.results`. List-bearing buckets in `impact.tiers`, `contracts.{http_routes,mcp_tools,event_handlers}`, `export.{nodes,edges}`, `communities.processes[*].members`, mermaid `diagram` (single string) all degrade pathologically. Scalar `impacted_count:int` stringified.
- **Verdict**: **KEEP+MERGE** — single rewrite collapses 4+ HIGH defects. Anti-overengineering OK because it REPLACES current buggy logic, doesn't add new abstraction.
- **Diff size**: ~80 lines `_shared.py::_apply_token_budget` rewrite.
- **Risk**: changes envelope shape for every tool. Need regression test per tool that hits truncation.
- [ ] Rewrite shrinker · [ ] regression tests · [ ] verify pytest · [ ] commit

### W6.3 — F6/B15/N1 [CRITICAL+HIGH, root-cause] File-level impact aggregation + detect_changes risk roll-up
- **Problem**: `impact(code:file:…)` returns `will_break=0` while `impact(code:class:contained, depth=3)` returns 55. `detect_changes(file, downstream=true)` returns risk=low based on same broken file-level walk. Two tools answer same Q with opposite verdicts.
- **Verdict**: **KEEP+MERGE** — F6/B15/N1 all collapse to same fix. Aggregate child-symbol breakage up to file uid.
- **Diff size**: ~30 lines `graph.py::cos_graph_impact` + detect_changes risk classifier.
- **Risk**: file impact responses get larger; need budget check.
- [ ] Implement aggregation · [ ] verify cross-tool agreement · [ ] commit

### W6.4 — T1/T2/B11 [HIGH] Path BFS — exclude external stubs + direction-aware
- **Problem**: paths hijack via `unresolved:str` (3 137 in-edges); edge direction not honored; zigzags through shared modules.
- **Verdict**: **KEEP+MERGE** — single BFS rewrite addresses all three.
- **Diff size**: ~40 lines `graph.py::cos_graph_path`.
- **Risk**: breaks rare legitimate paths that go through stubs (none seen).
- [ ] Add `exclude_kinds=["external"]` default · [ ] direction-flag edges · [ ] commit

### W6.5 — X7 [HIGH] Markdown link extractor — commonmark AST not regex
- **Problem**: regex captures backtick prose; emits 386 stale_paths + ranking pollution.
- **Verdict**: **KEEP** — high impact, narrow change. Use stdlib `re` with proper `\[…\]\(…\)` pattern (no new dep needed; commonmark/mistune would be overengineering for current scope).
- **Diff size**: ~15 lines `md_links.py` regex tightening.
- **Risk**: misses bracketed-but-non-markdown text — acceptable.
- [ ] Tighten regex to `\[[^\]]+\]\(([^)\s]+)\)` · [ ] reindex · [ ] verify stale_paths drops · [ ] commit

### W6.6 — B4/B5/B10 [HIGH] Export + communities silent-clobber
- **Problem**: `export max_nodes=500→0` (post-fetch trim removes nodes to fit edges); mermaid `diagram` replaced with sentinel; `communities top=50,members=20→33×1`.
- **Verdict**: **KEEP+MERGE** — all three are "shrinker over-clobbers single field"; folded into W6.2 plus per-tool guards.
- **Diff size**: ~20 lines additional per-tool guards (after W6.2 lands).
- [ ] Export nodes-first shrink · [ ] mermaid valid prefix or fail-validation · [ ] communities min members floor=3 · [ ] commit

### W6.7 — X2/X9 [HIGH] TOML + JSON dependency extraction
- **Problem**: pyproject.toml `[project].dependencies` (23 deps) + package.json `dependencies/devDependencies` (43 deps) emit ZERO dep nodes.
- **Verdict**: **KEEP** — supply-chain blast-radius is real value, not speculation. Two extractors share pattern.
- **Diff size**: ~30 lines per extractor; share `_emit_dep` helper.
- **Risk**: new edge type `requires` + new node uid scheme `pypi:package:*` / `npm:package:*`. Append-only schema.
- [ ] Add `requires` edge in extractors · [ ] reindex · [ ] verify counts · [ ] commit

### W6.8 — T3/N4 [HIGH] Context depth honesty + visit_limit scaling
- **Problem**: depth=2,3,4 byte-identical (TASK-036 SUMMARY mode depth-agnostic); visit_limit=50 doesn't scale with depth.
- **Verdict**: **KEEP** — silent lie. Cheap fix: scale visit_limit by depth, OR reject depth>2 with validation error.
- **Diff size**: ~10 lines.
- [ ] Scale visit_limit · [ ] OR reject depth>2 · [ ] verify · [ ] commit

### W6.9 — C1/C2/N3 [MEDIUM] Read-pool pragmas + busy_timeout reconcile
- **Problem**: `_get_read_conn` ignores `_apply_pragmas` SSOT (4 of 8 pragmas missing); busy_timeout 30000 set then overwritten to 5000.
- **Verdict**: **KEEP+MERGE** — three are one-liner each, share file.
- **Diff size**: ~5 lines `sqlite_backend.py`.
- [ ] Call `_apply_pragmas(read_conn)` · [ ] reconcile busy_timeout · [ ] commit

### W6.10 — T7 [MEDIUM] Dedupe folder `contains` edges
- **Problem**: 7× duplicate `contains` edges per folder pair (one row per extractor).
- **Verdict**: **KEEP** — 7× row inflation on folder spine pollutes centrality + edge counts.
- **Diff size**: ~5 lines — drop `extractor` column from UNIQUE key for `edge_type='contains'`. OR emit folder spine from ONE extractor only.
- **Risk**: schema migration needed if dropping from key.
- [x] **LANDED (TASK-038, 2026-05-28)** — deduped at the `upsert_edge` boundary (`contains` matches on (source,target,type) ignoring `extractor`; no migration) + repeatable `cos_graph_doctor(fix=True)` `duplicate_contains` cleanup. 703 redundant rows removed; `folder:tests` out-degree 148→74.

### W6.11 — F8/B8 [MEDIUM] Similar scorer — boost same-folder + demote tests when source non-test
- **Problem**: `similar(cos_graph_doctor)` returns 10 unrelated CLI-doctor tests. Label-only embedding ignores structure.
- **Verdict**: **KEEP** — small heuristic addition; no new dep.
- **Diff size**: ~15 lines `graph.py::cos_graph_similar`.
- [ ] Add same-file/same-folder boost · [ ] demote tests when source non-test · [ ] commit

### W6.12 — X8/X6 [MEDIUM] Pre-seed builtin TYPE_UIDS
- **Problem**: 43% of `has_param_type` → `unresolved:str/int/bool/dict`; `inherits_from` 17 → unresolved builtins.
- **Verdict**: **KEEP+MERGE** — single 20-line dict + lookup, fixes both.
- **Diff size**: ~25 lines `code_python.py`.
- [ ] Add BUILTIN_TYPE_UIDS dict · [ ] resolver shortcut · [ ] reindex · [ ] commit

### W6.13 — F2/F3/F13 [MEDIUM] rename_plan bucket routing
- **Problem**: test sites placed in `call_sites` not `test_references`; imports folded into call_sites (rooted in N2 fix); `has_param_type` mixed into call_sites array.
- **Verdict**: **KEEP** — after W6.1 (N2) lands, imports get separate edge_type. Then bucket-routing fix is small.
- **Diff size**: ~20 lines `graph.py::cos_graph_rename_plan`.
- **Depends on**: W6.1
- [ ] Route by source_uid path prefix `tests/` · [ ] separate import_sites + type_references buckets · [ ] commit

### W6.14 — F1/F4 [MEDIUM] Semantic_scope label on coverage tools
- **Problem**: rename_plan=28 vs impact=78 vs grep=94 disagreement is silent; context.depth=2 says calls=54 vs trace direct=10.
- **Verdict**: **KEEP** — pure meta addition, no algorithmic change.
- **Diff size**: ~15 lines across 4 tools.
- [ ] Add `meta.semantic_scope: "direct"|"transitive_depth_N"|"file_contains_only"` · [ ] commit

### W6.15 — T5 [MEDIUM] impact downstream — exclude contains, include is_decorated_by reverse
- **Problem**: downstream walk follows `contains` UP folder spine; misses real decorator-call-sites.
- **Verdict**: **KEEP** — graph correctness; fold with W6.3.
- **Diff size**: ~10 lines.
- [ ] Filter contains from downstream BFS · [ ] include is_decorated_by reverse · [ ] commit

### W6.16 — T9/F5 [LOW] Dedupe duplicate uids in top_edges_by_type
- **Problem**: same uid printed 4× in summary.
- **Verdict**: **KEEP** — cheap.
- **Diff size**: ~5 lines.
- [ ] Dedupe + add count field · [ ] commit

### W6.17 — B6 [LOW] centrality top=50→49
- **Verdict**: **KEEP** — one-line LIMIT alignment.
- [ ] Fix LIMIT · [ ] commit

### W6.18 — T11/B9 [LOW] communities surface downshift reason
- **Verdict**: **KEEP** — meta-only addition.
- [ ] Surface `members_downshifted_because` · [ ] commit

### W6.19 — F12 [LOW] trace external_targets builtin allowlist
- **Verdict**: **KEEP** — hardcoded set, no abstraction.
- [ ] Add BUILTIN_NAMES set, strip from external_targets · [ ] commit

### W6.20 — T8/F14 [LOW] resolve kind-weighting
- **Problem**: `"src/cli/main.py main"` returns wrong module; `SqliteBackend` returns substring-match noise.
- **Verdict**: **KEEP** — fold with existing G8/G9 kind-weighting.
- [ ] Strengthen kind boost · [ ] demote substring matches when exact-label exists · [ ] commit

### Drop / defer (anti-overengineering or low value)

- **X1** — REFUTED. **DROP**.
- **B12** — REFUTED. **DROP**.
- **X10** `handles_tool` semantic rename — **DEFER**: requires registry.yaml schema change for marginal gain. Re-evaluate when hook UI consumes the field.
- **X11** `.codex/config.toml` skipped — **DROP**: 5 files, not load-bearing. Add only if a consumer needs it.
- **X12** awaits silent skip on method-chain — **DROP**: covered by 36 honest edges; making invisible-failures visible adds noise without action.
- **X3** root-doc orphans — **DEFER**: covered after W6.5 markdown regex fix.
- **B3** contracts walks docstring example — **KEEP** but small: skip decorators inside docstring AST. Fold into W6.7 (~5 lines).
- **B7** ranking dominated by test fixtures — **KEEP** small: skip `tests/` paths (5 lines).
- **B13** unresolved orphan retry-link — **DROP**: extractor will re-emit on reindex; periodic sweep is overengineering.
- **B14** entrypoints diversify by dir — **DEFER**: cosmetic.
- **B16** context include_content slice wrong — **KEEP** small (10 lines).
- **B17** contracts events dedup — **KEEP** small.
- **C3** read-conn WeakValueDictionary — **DROP**: no observed leak; bounded in production. Defer until leak proven.
- **F9** rename `result_truncated`→`results_clamped` — **DROP**: naming churn for marginal clarity.
- **F10** communities = test-flow clusters — **DEFER**: filtering tests already addresses; full re-design overengineering.
- **F11** centrality boost for mcp_tool kind — **DROP**: degree centrality is what it is; adding "importance" weights = new concept.
- **T6** path hops vs edge count + frontier_saturated — **DROP**: collapses after W6.4.
- **T10** centrality betweenness kind filter — **KEEP** small (3 lines, honor existing `kind` arg).
- **T12** tokens_estimated honesty — **KEEP** small: cross-check envelope cap in shrinker (folds into W6.2).
- **X5** variable kind captures dataclass fields — **DEFER**: 611 noise but no current consumer breaking. New `field` kind = schema growth.

## Execution policy

1. **Wave order**: W6.1 → W6.2 → W6.3 → W6.4 → W6.5 → W6.6 → W6.7 → W6.8 → W6.9 → ... (priority order).
2. **One fix → one commit** (Rule 24). Title ≤100 chars, body ≤3 lines, no agent attribution.
3. **After each W**: targeted pytest (`uv run --extra graph_os pytest src/core/graph_os/tests/`); reindex if extractor touched (`cos graph-reindex --force --files <path>`); verify SQL counts; verify MCP tool envelope.
4. **Skill-load**: graph-explorer (primary), clean-code, python-meta-server already active.

## Verification matrix per wave

| Wave | Files | Test |
|---|---|---|
| W6.1 | `src/core/graph_os/extractors/code_python.py` | `pytest src/core/graph_os/tests/test_code_python.py test_i7_extractors.py -q` + reindex + SQL `SELECT COUNT(*) FROM graph_edges_v12 WHERE edge_type='imports'` |
| W6.2 | `src/core/thinking_os/tools/_shared.py` | `pytest src/core/graph_os/tests/test_mcp_tools.py -q` + per-tool char-count probe |
| W6.3 | `src/core/graph_os/tools/graph.py` | `pytest src/core/graph_os/tests/test_mcp_tools.py -q` + cross-tool agreement test |
| W6.4 | `graph.py::cos_graph_path` | path probe between distant uids; assert no `unresolved:*` in intermediate hops |
| W6.5 | `src/core/graph_os/extractors/md_links.py` | reindex + `cos_graph_doctor` stale_paths drops below 50 |
| W6.6 | `graph.py` export + communities | export(max_nodes=500) returns ≥1 node; communities min_members ≥3 |
| W6.7 | `code_toml.py` + `code_json.py` | new `dependency` kind nodes; ≥20 from pyproject; ≥40 from package.json |
| W6.8 | `graph.py::cos_graph_context` | depth=2 vs depth=3 returns different node counts |
| W6.9 | `sqlite_backend.py::_get_read_conn` | PRAGMA probe on read-pool conn shows cache_size=-65536 + mmap_size=268435456 |

## Resume marker

Triage complete. Active fixes: 20 waves (W6.1–W6.20). Drops: 13. Defers: 7. Ready to execute W6.1.
