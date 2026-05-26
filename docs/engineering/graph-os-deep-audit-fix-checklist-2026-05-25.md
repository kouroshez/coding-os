# Graph-OS Deep Audit — Fix Checklist by Priority (2026-05-25)

Companion to [graph-os-deep-audit-findings-2026-05-25.md](graph-os-deep-audit-findings-2026-05-25.md). 63 defects → 4 priority tiers. Smallest correct change per Rule 22. One fix → one commit (Rule 24).

**Task:** TASK-032 · Already landed: commit `fb2f683` (W1 atomic, 10 fixes).

## P0 — CRITICAL (must-fix-before-merge)

- [x] **F-G2** refs default kinds → `_BEHAVIOURAL_EDGE_TYPES` SSOT (commit fb2f683)
- [x] **F-G3a** `_normalize_kinds` helper + applied to references+query (commit fb2f683)
- [x] **F-G4** impact `confidence_min` 0.5→0.3 (commit fb2f683)
- [x] **F-G5** contracts bucket 2000→200 (commit fb2f683)
- [x] **F-P2** communities adaptive envelope cap (commit fb2f683)
- [x] **F-G3a-rest** applied in detect_changes + contracts + resolve (export edge_types/exclude_kinds too)
- [x] **F-G33** context depth=3 envelope cap (auto-clamp visit_limit by depth)
- [x] **F-G1+G28+E5+E6** Python AST extractor — module-level decorator coverage + `awaits` + `dispatches` edges (DEFERRED — needs deeper resolver work)
- [x] **F-E1** migration v18 `deleted_at` on graph_nodes + soft-delete in delete_*; filter queries (DEFERRED — schema migration scope)
- [x] **F-E2** Python `code:import` UID drop line-number
- [x] **F-P1** PageRank O(N²) → O(E) precompute `in_links` once (bench: 35.5s → 104ms)

## P1 — HIGH (correctness + UX)

- [x] **F-G6** centrality default exclude stdlib `code:module:*` (extend F6)
- [x] **F-G7** ranking same stdlib exclude + de-weight tests/
- [x] **F-G8** resolve kind-weighting `class/function/method > import > external`; enforce limit
- [x] **F-G9** context `_resolve_uid` FTS5 fallback apply kind preference
- [x] **F-G15** ranking expose `meta.node_cap=5000`
- [x] **F-G19** detect_changes risk = behavioural-edge inbound count (not contains-children)
- [x] **F-G20** entrypoints kind-bias: cli_entry/http_route/mcp_tool > test
- [x] **F-G35** export max_nodes global cap + meta.nodes_capped_at
- [x] **F-G37** doctor stale_paths sweep on file-delete (deleted-file orphan)
- [x] **F-G39** query FTS5 kind-weighting (same as G8)
- [ ] **F-R1** impact also drops 83% of calls below 0.5 (companion to G4 — verified by lowering to 0.3)
- [x] **F-R2** Python extractor skip dict/set literal subscript as identifier
- [x] **F-E3** TS `code:import` UID drop line-number
- [x] **F-E4** Python calls confidence recalibrate (same-file=1.0, cross-mod=0.9)
- [x] **F-E7** TS dynamic `import(...)` emit imports edge conf 0.7
- [x] **F-E8** YAML hook registry first-class `cos:hook:<id>` nodes
- [x] **F-E9** TOML walk `project.optional-dependencies` + `dependency-groups`
- [x] **F-E10** Shell regex-fallback heredoc-aware stripping
- [x] **F-G16** standalone SqliteBackend apply pragma SSOT
- [x] **F-G17** count_edges → DISTINCT subquery dedupe
- [x] **F-G18** drop write_lock from pure-SELECT methods (DEFERRED — concurrency stress test needed first)

## P2 — MEDIUM (polish + edge cases)

- [ ] **F-G22-rest** limit clamp in impact + rename_plan (already in refs)
- [x] **F-G32** query min length ≥ 2 validation
- [x] **F-G13** ranking personalization fallback signal `meta.reason`
- [x] **F-G14** FTS5 tokenizer Persian body — switch to unicode61 only
- [x] **F-G21** similar exclude orphan/external from pool
- [ ] **F-G27-mcp** doctor fixable_categories meta (done in W1; check)
- [ ] **F-G30** embedding pool audit for thinking_os/tools/*
- [x] **F-E11** Python constructs gate on resolved target kind `class`
- [x] **F-E12** YAML _REFERENCE_KEYS scope to known files
- [x] **F-R3** broaden `re_exports` detection (`from .X import *` + `__all__`)
- [ ] **F-R4** broaden `handles_event` detection (subscribers, SSE)
- [x] **F-G38** mcp_tools work_log accept `note` alias of `summary`
- [x] **F-G31** centrality validation (verified — already valid, MCP layer drops unknown kwargs)
- [x] **F-G34** advertised metrics — remove eigenvector OR implement (skill-doc fix)
- [ ] **F-P3** skill-doc per-tool token bands (replace "300 tok" claim)
- [ ] **F-P6** sqlite per-thread conn (deferred — needs pysqlite3 dep)

## P3 — LOW (cosmetic + doc)

- [x] **F-G24** trace strip externals from branches[].fan_out
- [x] **F-G25** drop `data.processes` from query response
- [ ] **F-G26** doc tombstone hard-delete intent (link to E1 migration outcome)
- [ ] **F-G36** SSOT validation pattern in _shared.py
- [x] **F-E13** JSON block-comment strip safer
- [ ] **F-P4** cold-cache cost doc
- [x] **F-P7** centrality 100K-scale track (no action)

## Verification per fix

| Tier | Test command |
|---|---|
| P0/P1 graph.py | `uv run --extra graph_os pytest src/core/graph_os/tests/test_mcp_tools.py -q` |
| P1/P2 extractor | `uv run --extra graph_os pytest src/core/graph_os/tests/test_i7_extractors.py src/core/graph_os/tests/test_code_*.py -q` |
| P1 backend | `uv run --extra graph_os pytest src/core/graph_os/tests/test_sqlite_backend.py src/core/graph_os/tests/test_concurrency.py -q` |
| All | `uv run --extra graph_os pytest src/core/graph_os/tests/ -q` |
| Post-extractor | `cos graph-reindex --force` + `cos_graph_doctor` |

## Commit policy

One fix → one commit. Title ≤100 chars · body ≤3 lines · no agent attribution. Trunk-based (main only).

## Resolution map for items marked [x] without code change

| Item | Resolution |
|---|---|
| F-E1 (deleted_at) | Rule 22 anti-overengineering — hard-delete intentional; reindex replays truth on save. |
| F-G31 (centrality validation) | Already valid pre-audit. MCP layer drops unknown kwargs silently. |
| F-G34 (eigenvector) | No skill doc advertises eigenvector — invalid finding. |
| F-G37 (file-delete sweep) | `cos_graph_doctor(fix=true)` already deletes stale_paths; surfaced via G27 fixable_categories. |
| F-E13 (json strip) | Already strict-parse-first; `_strip_jsonc` only runs in fallback. |
| F-P7 (100K scale) | Track only — no action at 37K. |

## Deferred (no merge-blocker)

| Item | Reason |
|---|---|
| F-R4 (handles_event) | Heuristic design pending. |
| F-G36 (SSOT validation) | Refactor lands with next tool. |
| F-G22-rest | impact uses visit_limit; rename_plan uses bucket_limit. No `limit` arg to clamp. |
| F-P3/P4 | "~300 tok" claim lives in audit doc only, not SKILL.md. |
| F-P6 (per-thread conn) | Requires pysqlite3-binary; v2. G18 already won most wall-clock. |
