# Graph-OS Round 4 Fix Checklist — Wave 7 (2026-05-27)

Companion to [graph-os-round4-audit-findings-2026-05-27.md](graph-os-round4-audit-findings-2026-05-27.md). 34 new defects (R4-01..R4-26 + R4-N5..R4-N12); triaged against Rule 22 (anti-overengineering). One fix → one commit (Rule 24). Apply top-down.

## Triage principles

- **Collapse:** multiple surface defects sharing one root cause → ONE fix.
- **Validator helpers FIRST**: shared `_validate_*` in `_shared.py` eliminates 11 silent-param defects at once.
- **CRITICAL before HIGH**: R4-01 (fuzzy-resolve hijack) blocks correctness of every uid-accepting tool.
- **Skip:** taxonomy renames that don't unblock any consumer (defer to next quarter).

## Wave 7 (priority order)

### W7.1 — R4-03/04/05/06/07/08/09/16/19/20/26 [HIGH, root-cause] Shared validator helpers in `_shared.py`

- **Problem**: 11 separate silent-param defects across `communities/export/ranking/trace/query/resolve/centrality/impact` — params accepted then ignored, or out-of-range silently degraded.
- **Verdict**: **KEEP+MERGE** — single helper module collapses all 11. Diff replaces existing inline-validation with shared functions; no new abstraction added (refactoring existing scattered checks).
- **Diff size**: ~60 lines added to `src/core/thinking_os/tools/_shared.py` + ~3 lines per `cos_graph_*` tool to call them = ~110 lines.
- **Helpers**:
  - `_validate_positive_int(name, value)` — `top, limit, max_steps, iterations, min_size, max_members, depth`
  - `_validate_confidence(name, value)` — `confidence_min` in `[0.0, 1.0]`
  - `_validate_query_min_chars(q, min=2)` — for `query` AND `resolve` parity
  - `_validate_uid_or_path(uid)` — must be `^(code:|doc:|folder:|cos:|community:)` or contain `/` (for raw paths). NOT bare identifier.
  - `_validate_kind(name, value, known_kinds)` — reject if known_kinds non-empty and value not in set; OR emit `meta.kind_unknown=true`
  - `_validate_edge_type(name, value, known_edge_types)` — same shape, cross-check against `SELECT DISTINCT edge_type FROM graph_edges_v12`
- **Risk**: changes envelope shape for malformed-input cases (fail-validation instead of ok-empty). Update tests that assumed silent empty.
- [ ] Add helpers · [ ] wire into all 17 cos_graph_* tools · [ ] update regression tests · [ ] commit

### W7.2 — R4-01 [CRITICAL] Fuzzy-resolve guard for uid-accepting tools

- **Problem**: `cos_graph_impact("garbage")`, `cos_graph_similar("xyz")`, etc. silently fall through to FTS5 fuzzy match and return a plausible blast radius for an unrelated symbol.
- **Verdict**: **KEEP** — load-bearing CRITICAL. Single rule: if input doesn't match `^(code:|doc:|folder:|cos:|community:)` AND doesn't contain `/` or `.py$`/`.md$`/`.go$` extension, reject as `validation` error OR emit `meta.resolved_from: "fuzzy_fallback"` (preferred — agent can decide).
- **Diff size**: ~20 lines in `_resolve_uid` helper used by `impact, similar, context, references, rename_plan, trace, path`.
- **Risk**: breaks workflows that intentionally pass NL strings. Audit any consumer; emit warning instead of error initially.
- [ ] Tighten fallback · [ ] add `meta.resolved_from` · [ ] commit

### W7.3 — R4-02 [CRITICAL] Per-kind default `kinds` for `cos_graph_references`

- **Problem**: Default `kinds="calls,accesses_field,imports,references_doc"` returns 0 for any class (which uses `constructs`); agent reads 0 → assumes dead symbol.
- **Verdict**: **KEEP** — load-bearing CRITICAL.
- **Diff size**: ~25 lines in `cos_graph_references`. Build `DEFAULT_KINDS_BY_NODE_KIND = {"class": [...], "function": [...], "method": [...], "module": [...]}` table.
- **Risk**: changes returned counts for class queries. Update tests.
- [ ] Per-kind default kinds · [ ] regression test for class · [ ] commit

### W7.4 — R4-N5 [HIGH] community: node registration OR UI guard

- **Problem**: `cos_graph_communities` emits `community:<sha1[:12]>` ids; UI clicks → backend rejects. 0 community: nodes in `graph_nodes`.
- **Verdict**: **TWO-PHASE FIX:**
  - **Phase A (cheap, ship now)**: UI guard in `src/core/web/ui/src/features/graph/useSigma.ts:249` — `if (e.node.startsWith('community:')) return;` before `options.onNodeClick`. ~3 lines.
  - **Phase B (correct, scope to next task)**: register Louvain processes as `kind='community'` first-class nodes during community computation; emit `member_of_community` edges from members; resolver accepts the scheme.
- **Diff size**: A: 3 lines. B: ~80 lines.
- **Risk**: A loses click-to-context UX for communities (but it was broken anyway); B is bigger but cleaner.
- [ ] Phase A guard · [ ] commit · [ ] file Phase B as TASK-NNN

### W7.5 — R4-N7 [HIGH] reindex prune mode for stale nodes

- **Problem**: W6.5 markdown extractor patched but 339 pre-existing stale doc_file nodes remain (227 moved + 7 malformed + ~105 deleted + ~105 golden-sandbox).
- **Verdict**: **KEEP** — un-blocks doctor `healthy=true` after suppressing expected-noise.
- **Diff size**: ~40 lines.
- **Implementation**:
  - `cos graph-reindex --prune-stale` flag: walk `SELECT uid, file_path FROM graph_nodes WHERE file_path IS NOT NULL`; for each, check `Path(file_path).exists()`; if not, DELETE. ON DELETE CASCADE drops edges.
  - Doctor `fix=True` extends `fixable_categories` to include `stale_paths` actually (today it lists self_loops which aren't even an issue).
- **Risk**: deletes nodes for files that were moved (not deleted). Mitigation: detect moves first — `SELECT label FROM graph_nodes WHERE file_path=A` matches by basename to another current file → emit migration UPDATE, not DELETE.
- [ ] Add --prune-stale CLI flag · [ ] doctor fixable_categories · [ ] regression test · [ ] commit

### W7.6 — R4-N9/N10/13/25 [MEDIUM] doctor health threshold + categories

- **Problem**: doctor `healthy=false` lumps expected-noise orphans (stdlib refs) with real bugs; `fixable_categories` lies; UI badge has no context.
- **Verdict**: **KEEP+MERGE** — 4 LOW defects share one root.
- **Diff size**: ~50 lines in `cos_graph_doctor`.
- **Implementation**:
  - Categories: `orphaned_external_unresolved` (suppress from count), `orphaned_inrepo_real` (count), `malformed_uid_path` (new — paths with `../`), `stale_paths_moved`, `stale_paths_deleted`.
  - `healthy = orphaned_inrepo_real == 0 AND malformed == 0 AND stale_deleted == 0` — externals + suppression OK.
  - `fixable_categories` actually reflects what `fix=True` will do today.
  - Hub UI hover tooltips per category with semantics + fix-suggestion (separate UI commit).
- [ ] Recompute categories · [ ] honest fixable list · [ ] commit

### W7.7 — R4-N6 [MEDIUM] Dep-extraction taxonomy fix

- **Problem**: 44 npm + 31 pypi nodes emit with `kind=doc_external` (category error). [project.optional-dependencies] arrays under-covered.
- **Verdict**: **KEEP** — finishes W6.7 properly.
- **Diff size**: ~30 lines across `code_json.py` + `code_toml.py`.
- **Implementation**:
  - New `kind='dependency'` (or reuse `kind='package'` if it exists — check).
  - Walk `[project.optional-dependencies]` groups in pyproject.toml.
  - Edges: `imports` from the project's pyproject.toml/package.json file to the package node (existing pattern) + `declares` from the config to the project node.
- [ ] kind rename · [ ] optional-deps walk · [ ] reindex · [ ] verify counts · [ ] commit

### W7.8 — R4-12/24 [MEDIUM] Stub-hub exclude list for path BFS

- **Problem**: `__future__`, `typing`, `typing_extensions`, `__init__` are in-repo `code:module:*` nodes (not `code:external:*`) and bridge unrelated nodes in `cos_graph_path` BFS. T1 fix excluded externals but not in-repo stubs.
- **Verdict**: **KEEP** — small narrow fix; collapses two surface defects.
- **Diff size**: ~10 lines `cos_graph_path`.
- **Implementation**: extend exclude set with `STUB_MODULES = {"__future__", "typing", "typing_extensions", "__init__"}`; skip nodes whose module-part matches.
- [ ] Extend exclude · [ ] regression test on known hub-bridge case · [ ] commit

### W7.9 — R4-03/17 [MEDIUM] communities count + min_size consistency

- **Problem**: `min_size` silently ignored; `top=5, members=10` returns `count=15` (inflated past request).
- **Verdict**: **KEEP+MERGE** — one tool, two related bugs.
- **Diff size**: ~15 lines.
- **Implementation**:
  - Wire `min_size` into post-Louvain filter.
  - Cap `count <= top_requested` strictly; if rebalance shifts, surface in `meta.top_after_rebalance` not `count`.
- [ ] Apply min_size · [ ] cap count · [ ] commit

### W7.10 — R4-14/N8 [LOW] Remove cos_graph stub completely

- **Problem**: `cos_graph` removed but stub still registered; pollutes `tools/list` + `cos_graph_contracts` + inflates "17 tools" claim.
- **Verdict**: **KEEP** — migration deadline past (audit predates fix-checklist).
- **Diff size**: ~5 lines (delete stub + decorator).
- **Implementation**: delete `def cos_graph(...)` and its `@mcp.tool` decorator from `src/core/thinking_os/server.py`; reindex graph; verify `cos:mcp_tool:cos_graph` node disappears from contracts.
- [ ] Delete stub · [ ] reindex · [ ] verify · [ ] commit

## Drop / defer

| ID | Reason |
|---|---|
| R4-10 (contracts dedup test-fixtures) | DEFER — small contract bug, low surface |
| R4-11 (entrypoints envelope) | KEEP small — folds into W6.2 next iteration; document as known limit for top>50 |
| R4-15 (mixed-script FTS5) | DEFER — Persian-only works; mixed-script is corner case |
| R4-18 (rename_plan no-op same name) | KEEP small — 3-line guard; fold into W7.1 |
| R4-21 (context depth=99) | KEEP small — re-stamp existing W6.8 fix-checklist as still active |
| R4-22 (export max_nodes=3 no edges) | KEEP small — require root_uid OR document |
| R4-23 (DOT label escape) | KEEP small — defensive |
| R4-N11 (NodeInspector vs ContextPanel shape drift) | DEFER — works today; consolidate when next UI refactor |
| R4-N12 (debounce filename) | DROP — hygiene only, no functional impact |

## Verification matrix per wave

| Wave | Files | Test |
|---|---|---|
| W7.1 | `src/core/thinking_os/tools/_shared.py` + 17 cos_graph_* sites | `pytest src/core/graph_os/tests/test_mcp_tools.py -q` + new validator tests |
| W7.2 | `_shared.py::_resolve_uid` | probe `cos_graph_impact("garbage")` → expect validation error OR `meta.resolved_from=fuzzy_fallback` |
| W7.3 | `cos_graph_references` | probe class uid → expect non-zero `constructs` callers |
| W7.4 (A) | `src/core/web/ui/src/features/graph/useSigma.ts` | click community node → no error |
| W7.5 | `src/cli/graph_commands.py` + doctor | run `cos graph-reindex --prune-stale` on test DB; verify stale count = 0 |
| W7.6 | `cos_graph_doctor` | probe → expect `healthy=true` when only external-unresolved orphans present |
| W7.7 | `code_json.py` + `code_toml.py` | reindex; SQL `SELECT COUNT(*) FROM graph_nodes WHERE kind='dependency'` ≥ 75 |
| W7.8 | `cos_graph_path` | probe `path(sqlite_backend.py, cli/main.py)` → expect no `__future__` intermediate |
| W7.9 | `cos_graph_communities` | probe `min_size=1000` → expect `[]` or filter applied |
| W7.10 | `src/core/thinking_os/server.py` | `ToolSearch("select:cos_graph")` → not found |

## Execution policy

1. **Wave order**: W7.2 → W7.3 (CRITICAL first) → W7.1 (validators unblock the rest) → W7.4 → W7.5 → W7.6 → W7.7 → W7.8 → W7.9 → W7.10.
2. **One fix → one commit** (Rule 24). Title ≤100 chars, body ≤3 lines, no agent attribution.
3. **After each W**: targeted pytest matrix command (`uv run --extra graph_os pytest src/core/graph_os/tests/`); reindex if extractor touched.
4. **Reviewer subagent re-grep**: after all 10 fixes land, run reviewer subagent with the R4 register; predicates verify (counts_after_zero, reviewer_check pass).

## Resume marker

Triage complete. Active waves: 10 (W7.1..W7.10). Drops: 1 (R4-N12). Defers: 3 (R4-10, R4-15, R4-N11). Ready to execute W7.2 (CRITICAL fuzzy-resolve guard).
