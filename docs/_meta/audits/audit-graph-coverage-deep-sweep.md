<!-- domain:ALL | layer:engineering | ssot:false | updated:2026-05-23 -->
# Audit — Graph Coverage Deep Sweep (2026-05-23)

> Exhaustive review of `cos_graph_*` MCP tool coverage signals after
> the `_shared.ok` stripping discovery. Triggered by the user's
> "" mandate.

## Mandatory category table

| # | Category | Tool / artefact | Count BEFORE | Count AFTER |
|---|---|---|---:|---:|
| 1 | Silent `results[:limit]` truncation, no signal | `cos_graph_query` | 1 | 0 |
| 2 | Silent `scored[:top_k]` truncation, no signal | `cos_graph_similar` | 1 | 0 |
| 3 | Silent per-bucket `limit=500` truncation (CRITICAL — rename plan must be exhaustive by design) | `cos_graph_rename_plan` | 3 buckets | 0 |
| 4 | Silent `len(steps) < max_steps` cap, no signal | `cos_graph_trace` | 1 | 0 |
| 5 | Silent per-bucket `limit=2000` cap, no signal | `cos_graph_contracts` | 3 buckets | 0 |
| 6 | Silent `_walk_bfs visit_limit=500` (default) on deep walk, no signal | `cos_graph_detect_changes` | 1 | 0 |
| 7 | Silent `eps[:top]` truncation, no signal | `cos_graph_entrypoints` | 1 | 0 |
| 8 | Test gap — `stale_paths` doctor detector has zero pytest coverage | `cos_graph_doctor` | 0 tests | ≥1 test |
| 9 | Test gap — 8-bucket auto-blend (doc_link / decoration) untested | `cos_graph_export` | 0 tests | ≥1 test |

## Root cause discoveries

### A. `_shared.ok` strips caller-supplied `truncated` (already fixed in prior commit)

`thinking_os.tools._shared.ok` strips and overwrites `meta.truncated`
purely based on token-budget. Every tool that set `meta.truncated=True`
for COVERAGE truncation had it silently flipped back to False whenever
the response fit in budget — which is always for small probes.

Fix landed pre-audit: graph tools now use `walk_truncated` /
`result_truncated` keys distinct from envelope's `truncated`.

### B. Seven additional graph tools silently truncate with NO signal

Discovery via grep on every `cos_graph_*` function body for the pattern
`limit\s*=` paired with absence of `truncated` in same function. Found
in categories 1–7 above.

## Scope (files touched by remediation)

- `src/core/graph_os/tools/graph.py` — 7 tool functions
- `src/core/graph_os/tests/test_mcp_tools.py` — coverage pytest cases
- `src/core/graph_os/tests/test_smart_export.py` — stale_paths + doc_link bucket
- `docs/_meta/audits/audit-graph-coverage-deep-sweep.md` — this file

## Verification protocol per category

For each row in the table:

1. Grep BEFORE — confirm bug exists.
2. Apply fix — add coverage signal in canonical envelope:
   - `meta.<X>_truncated` (`result_` for limit-on-results, `walk_` for BFS cap)
   - `data.total_count` or `data.<bucket>_total_count` where applicable
   - Limit knob exposed if hardcoded.
3. Grep AFTER — assert 0 remaining silent truncations.
4. Pytest pin — assert the signal fires under tight budget AND stays
   false under generous budget.

## Resume Marker

- 2026-05-23 — audit complete. 9 categories pinned, all remediated:
  - 7 truncation-signal additions (`cos_graph_query`, `_similar`,
    `_rename_plan`, `_trace`, `_contracts`, `_detect_changes`,
    `_entrypoints`).
  - 2 test gaps closed (`stale_paths` detector + 8-bucket auto-blend).
  - 8 new pytest cases pin the truncation contract; 7 new pytest
    cases pin the 8-bucket + stale-paths contracts.
  - Final pytest count: **662 passed (+15 from baseline 647)**.
  - Re-grep AFTER on the 7 fixed tools: **0 silent-truncation
    patterns remaining**.

## ExhaustiveEvidence

```
counts_before = {
  silent_truncation_tools: 7,
  test_gap_features: 2,
}
counts_after = {
  silent_truncation_tools: 0,
  test_gap_features: 0,
}
categories_covered = [
  "cos_graph_query.result_truncated",
  "cos_graph_similar.result_truncated",
  "cos_graph_rename_plan.result_truncated + per-bucket totals",
  "cos_graph_trace.walk_truncated",
  "cos_graph_contracts.result_truncated + per-edge-type",
  "cos_graph_detect_changes.walk_truncated",
  "cos_graph_entrypoints.result_truncated",
  "cos_graph_doctor.stale_paths pytest",
  "cos_graph_export.auto-blend doc_link + decoration pytest"
]
gaps_remaining = []
```
