---
id: TASK-122
title: "TASK-080d: Add provenance field to GraphEdge + A/B flag in cos graph-reindex"
swimlane: graph_os
kind: refactor
epic: graph_os-the upstream scope-resolution implementation
labels: []
status: complete
priority: P3
appetite: "1d"
created: 2026-04-25
started: 2026-04-25
completed: 2026-04-25
agent_session: null
depends_on: []
blocked_by: []
references: []
---
# TASK-122: TASK-080d: Add provenance field to GraphEdge + A/B flag in cos graph-reindex

**Outcome (one sentence):** Every emitted GraphEdge carries a stable, single-string `provenance` value (`tree-sitter` / `ast` / `regex` / `lsp` / `text-search`) in metadata, and `cos graph-reindex --extractor=tree-sitter|legacy|auto` lets operators force the parser ladder for A/B rollout of TASK-119/120/121 — defaulting to `auto` (today: legacy primary, tree-sitter overlay).

## Read First
- [core/graph_os/types.py](../../core/graph_os/types.py) — GraphEdge.metadata is the carrier (no schema migration needed).
- [core/graph_os/extractors/code_python.py](../../core/graph_os/extractors/code_python.py) — emits 0.9 confidence ast edges; tag with `provenance: ast` baseline.
- [core/graph_os/extractors/code_ts.py](../../core/graph_os/extractors/code_ts.py) — regex baseline; tag with `provenance: regex`.
- [core/graph_os/extractors/code_go.py](../../core/graph_os/extractors/code_go.py) — regex baseline; tag with `provenance: regex`.
- [cli/graph_commands.py](../../cli/graph_commands.py) — `graph-reindex` lives here.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** any extractor emits an edge today
- **When** the new `provenance` helper is integrated
- **Then** the edge's `metadata` carries a `provenance` key with one of: `tree-sitter` / `ast` / `regex` / `lsp` / `text-search` — back-compat preserved for callers that don't read it.
- **Given** a user runs `cos graph-reindex --extractor=tree-sitter`
- **When** the dispatcher loads an extractor whose tree-sitter grammar is available
- **Then** the dispatcher honours the preference (or fails fast with `validation` envelope if unavailable); `--extractor=auto` keeps current behaviour.
- **Given** existing test suites (code_python, code_ts, code_go, contracts)
- **When** they run unchanged
- **Then** every test still passes — provenance is additive, never replaces existing fields.

## Work Log

- 2026-04-25 — Shipped:
  - `provenance_for(extractor)` + `PROVENANCE_VALUES` in
    [core/graph_os/types.py](../../core/graph_os/types.py) — closed
    7-value vocabulary (`tree-sitter`, `ast`, `regex`, `lsp`,
    `text-search`, `parser`, `unknown`).  Future extractor IDs
    (`code_python_ts@v1`, `code_ts_ts@v1`, `code_go_ts@v1`) already
    pre-mapped so TASK-119/120/121 light up provenance="tree-sitter"
    automatically when they ship.
  - `_edge_to_dict` in [core/graph_os/tools/graph.py](../../core/graph_os/tools/graph.py)
    surfaces `provenance` alongside `extractor` — additive, never
    replaces.  Hub UI Inspector (Impact / 360°) consumes it for
    free; `curl /api/graph/impact/...` confirmed `provenance: "ast"`
    on live data.
  - `cos graph-reindex --extractor=auto|legacy|tree-sitter` flag in
    [cli/graph_commands.py](../../cli/graph_commands.py).  Click
    rejects garbage values; the chosen ladder is published via
    `COS_EXTRACTOR_PREFERENCE` so the future TASK-119/120/121
    extractors can read it without a signature change.
- Tests: [core/graph_os/tests/test_provenance.py](../../core/graph_os/tests/test_provenance.py)
  — 21 cases covering closed vocabulary, mapping correctness for
  every shipped + future extractor ID, unknown / None / empty input
  fallbacks, registry-wide assertion that no entry escapes the
  vocabulary, `_edge_to_dict` surface, and CLI-flag publication +
  validation of the env var.
- Verification:
  - `pytest core/graph_os/tests/ -q` → 562 passed / 3 skipped (was
    541 → +21 net new). Zero regressions.
  - `pytest core/thinking_os/tests/ -q` → 1012 passed.
  - `pytest tests/test_cli.py -q` → 49 passed.
  - `pytest tests/test_adapters.py tests/test_adapter_parity.py -q`
    → 47 passed (one stale assertion fixed: TestMcpPortable —
    `cos-mcp-start` is the canonical entry per CLAUDE.md rule 20).
  - `make verify-hooks` → green.
  - End-to-end: `cos graph-reindex --extractor=tree-sitter --status`
    accepted, `--extractor=invalid-foo` rejected with `validation`
    error.  Live `/api/graph/impact/<discover-uid>` returns
    `provenance: "ast"` on every contained edge.
- 2026-04-25 [claude]: Status transitioned to complete via cos task-done.

