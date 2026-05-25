# Audit — Graph OS Deep Re-Audit + Bench (2026-05-25)

**Task:** TASK-032 · **Status:** in_progress
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
