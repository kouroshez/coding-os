---
audit_id: graph-os-deep-2026-05-25
task_id: TASK-032
status: complete
created: 2026-05-25
completed: 2026-05-27
predicates: [counts_after_zero, reviewer_pass, evidence_bundle_submitted]
matched_exhaustive: [" graph", "", "", ""]
---

# Audit — Graph OS Deep Re-Audit + Bench (2026-05-25)

**Task:** TASK-032 · **Status:** complete
**Trigger:** user exhaustive intent — " graph", "", "", ""
**Scope:** post-TASK-029 verification + deepening of all 17 `cos_graph_*` MCP tools, extractors (Py/TS/Go/Shell/MD/YAML/JSON/TOML), SQLite backend, reindex dispatch, envelope contract, perf bench, new defect surface.
**Prior:** [audit-graph-os-exhaustive-2026-05-24.md](audit-graph-os-exhaustive-2026-05-24.md) — 19 findings · [fix-checklist](audit-graph-os-fix-checklist-2026-05-24.md) — 14 fixes landed.

## Pointer (per Rule 14)

The full defect register lives in [docs/engineering/graph-os-deep-audit-findings-2026-05-25.md](../../engineering/graph-os-deep-audit-findings-2026-05-25.md) (28 defects, 5 CRITICAL / 13 HIGH / 6 MEDIUM / 4 LOW).

## Baseline (2026-05-25 pre-audit)

- nodes: 36 987 · edges: 73 867
- doctor `healthy=false` — 1 category remains (orphaned_nodes=873 — all `code:external:unresolved:*`, intentional per F14 disposition).
- self_loops: 0 ✅ (F12) · stale_paths: 0 ✅ (F13)
- pytest `src/core/graph_os/tests/`: **682 pass / 16 skip / 0 fail** in 24.75 s.

## Methodology

Parallel diagnostic subagents (backend, deep-tool smoke, extractor parity, perf bench) + direct MCP probes (38+ calls, all 17 tools exercised) + direct SQL on `.coding-os/coding-os.db` + reviewer subagent.

## F1–F14 verification snapshot

| F# / # | Status | Note |
|---|---|---|
| F1/#2 resolve column-order | ✅ HOLDS | All 5 sites in sqlite_backend + 4 in graph.py emit identical column order; `_row_to_node` aligned. |
| F2/#6 rename_plan kinds | ✅ HOLDS | `_BEHAVIOURAL_EDGE_TYPES` SSOT in place; rename_plan returns 33 sites for SqliteBackend. **BUT** references default kinds not aligned → see G2. |
| F3/#19 communities docstring | ✅ HOLDS | "processes" key + description aligned. |
| F4/#5 impact tier semantic | ⚠️ PARTIAL | will_break excludes `contains` (✅) but `confidence_min=0.5` drops constructs (conf=0.4) → see G4. |
| F5/#14 _safe_id collision | ✅ HOLDS | sha1 suffix in mermaid/dot — verified per-class export. |
| F6/#10+#11 centrality/ranking noise | ⚠️ PARTIAL | `code:external:*` excluded; stdlib `code:module:<name>` still surfaces → see G6, G7. |
| F7/#12 ranking personalization | ⚠️ PARTIAL | Multi-word EN works; Persian silently falls back without warning → see G13. |
| F8/#9 communities cap | ✅ HOLDS | max_members=10; tokens_estimated 4 766 for top=5 (below MCP cap). |
| F9/#7 trace external filter | ⚠️ PARTIAL | `external_targets` array populated (✅) but externals still in `branches[].fan_out` → see G24. |
| F10/#13 entrypoints diversity | ⚠️ PARTIAL | File-diverse but kind-diverse missing (all top-10 are tests) → see G20. |
| F11/#17 context FTS5 fallback | ⚠️ PARTIAL | Fallback works but lacks kind preference; unqualified label resolves to doc heading instead of code → see G9. |
| F12/#3 self-loop drop | ✅ HOLDS | doctor `self_loops=0`; SQL confirms 0 rows. |
| F13/#4 stale-paths | ✅ HOLDS | doctor `stale_paths=0`. |
| F14/#16 reindex tombstone | ✅ HOLDS | server.py shim entry visible in graph contracts. |

8/14 hold cleanly; 6/14 partially regressed or only addressed one half of the original defect class.

## Coverage statement

- Read full source: `src/core/graph_os/tools/graph.py` (selected ranges), `src/core/graph_os/backends/sqlite_backend.py` (full), `src/core/thinking_os/database.py` (migrations).
- pytest matrix: 682 pass / 16 skip / 0 fail.
- Direct MCP: every `cos_graph_*` tool exercised ≥1 time with happy + edge-case input.
- Direct SQL: 12 queries against `.coding-os/coding-os.db`.
- Subagents: 4 parallel (backend / deep-tool / extractor / perf), 3 completed; reviewer pending.

## Resume marker

All 4 subagents complete. **63 total defects** (8 CRITICAL · 26 HIGH · 16 MEDIUM · 13 LOW). Reviewer 9/9 critical PASS + R1-R4 new. Perf bench surfaced 7 more incl. **cos_graph_ranking 70× over latency target (P1)** + **cos_graph_communities 47K-token envelope lie (P2)**. Audit pass read-only; fix waves W1-W5 deferred to follow-up commits per Rule 22.


---

## Round 3 (2026-05-26) — TASK-037

**Pointer (per Rule 14):** Full Round 3 register lives in [docs/engineering/graph-os-round3-audit-findings-2026-05-26.md](../../engineering/graph-os-round3-audit-findings-2026-05-26.md) (58 new defects, 2 CRITICAL · 18 HIGH · 18 MEDIUM · 20 LOW/INFO).

**Trigger:** user exhaustive intent — " graph ", "", "", "".
**Methodology:** 5 parallel diagnostic subagents (deep-traversal, extractor-parity, envelope-budget, concurrency-stress, persona-flow) + reviewer subagent. Live probes against `.coding-os/coding-os.db` (37 617 nodes / 76 285 edges raw / 75 581 deduped).

### Baseline (2026-05-26)
- nodes 37 617 · edges raw 76 285 / deduped 75 581 (G17 working) · evidence 40 498
- doctor `healthy=false` — 1 061 orphans + 386 stale_paths (F13 surface regression)
- pytest `src/core/graph_os/tests/`: 686 pass / 16 skip / 0 fail in 17.25 s
- 4× tree-sitter-go grammar skips (Go extractor AST-driven path absent)

### Defect totals
- **58 new defects**: T1-T12 (12) deep-traversal · X1-X12 (12) extractor · B1-B17 (17) envelope · C1-C3 (3) concurrency · F1-F14 (14) persona
- Severity: **2 CRITICAL** (F3 rename_plan misses imports · F6 detect_changes lies risk=low) · **18 HIGH** · **18 MEDIUM** · **20 LOW/INFO**

### Top 5 cross-cutting root causes
1. **Envelope shrinker only walks `data.results`** — collapses B1/B2/B4/B5/B10/T4/F7. G5 was patched at the symptom not at root.
2. **Decorator + builtin type resolver leaks to external stubs** — collapses X1/X6/X8 (root cause of G1's 95% miss).
3. **Markdown link regex over-captures backtick prose** — collapses X7 + G37 residual + B13. Root cause of 386 stale_paths.
4. **Silent param overrides** (context depth ignored, communities members→1, export max_nodes→0, trace fuzzy auto-resolves to different file) — collapses T3/B6/B9/B10/B12/F8.
5. **Cross-tool answer disagreement unflagged** — rename_plan=28 / impact=78 / grep=94 / detect_changes=low for same Q. Add `meta.semantic_scope`. Collapses F1/F4/F6/B15.

### Verifications PASS (Round 3)
- P6 thread-local read conns deliver 1.74× speedup; 0 lock errors at 32 threads
- TASK-036 `cos_graph_context` SUMMARY at depth≥2 with `drill_hint`
- G17 count_edges DISTINCT dedupe correct (76 285 raw → 75 581 distinct)
- G29 path no-dup-consecutive invariant holds · G21 similar excludes orphans
- G31/G36 centrality validation rejects bogus metric · G32 query rejects q<2 chars
- G14 Persian FTS5 body content works · E8/E10 extractor fixes hold
- FTS5 sync exact (37 617=37 617) · no background indexer runaway

### Coverage statement
17/17 tools × default + extreme args = ~110 probes · per-tool char-count vs `meta.tokens_estimated` measured · 32-thread reader + 16-thread writer + reindex-while-query stress · PRAGMA SSOT verified primary AND read pool (gap surfaced — C1) · all 4 persona flows simulated with cross-tool numeric reconciliation · 5 parallel diagnostic subagents + reviewer subagent.

### Suggested commit waves (Round 3 — apply after reviewer PASS)
W6 envelope shrinker per-tool strategy · W7 `meta.semantic_scope` · W8 resolver bullseye (builtin types + decorator targets + commonmark links) · W9 silent-override loudness · W10 rename_plan imports + test bucket · W11 read-pool `_apply_pragmas` · W12 polish (~20 LOW/INFO items).

### Reviewer verdict (12 critical claims re-grepped)
- **8 CONFIRMED**: T1 (3 137 in-edges) · T3 (byte-identical depths) · T4 (53 642 bytes + `impacted_count:str` type break) · X2 (0 dep nodes vs 23 grep) · X7 (10 garbage uids) · F6 (file=low vs class=55 contradiction) · B1/B2 (116 640 bytes contracts) · C1 (4 pragmas missing in read pool)
- **2 PARTIAL**: T7 (2 rows not "per pair"), F3 (imports present but mis-encoded — root cause N2)
- **2 REFUTED**: X1 (0 edges found), B12 (trace exact-resolved, no file jump)
- **4 NEW (N-series)**: N1 file-level impact broken (will_break=0 for file but =55 for class) · **N2 HIGH Python AST encodes `from … import X` as `edge_type=calls`** (corrupts every downstream consumer) · N3 read vs write busy_timeout 6× drift · N4 visit_limit=50 doesn't scale with depth

### Post-reviewer totals
- Active: **58** (60 minus 2 REFUTED) · Severity: **1 CRITICAL** (F6) · **20 HIGH** · **18 MEDIUM** · **19 LOW/INFO**
- Highest-impact new finding: **N2** — imports upstream-encoded as `calls` corrupts semantic of every `calls` edge

### Resume marker
5 diagnostic subagents + reviewer complete. 58 active defects logged. ExhaustiveEvidence submission pending.
