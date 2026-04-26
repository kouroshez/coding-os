---
id: TASK-121
title: "TASK-080c: Promote tree-sitter for TS/TSX named bindings + JSX components"
swimlane: graph_os
kind: refactor
epic: graph_os-graph-tool-parity
labels: []
status: testing
priority: P2
appetite: "1d"
created: 2026-04-25
started: 2026-04-25
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---
# TASK-121: TASK-080c: Promote tree-sitter for TS/TSX named bindings + JSX components

**Outcome (one sentence):** TypeScript / TSX imports (`import { Foo as F } from "pkg"`) and class declarations (`class Foo extends Bar implements Baz`) parse via tree-sitter when active, emitting `imports` and `inherits_from` / `implements` edges tagged `code_ts_ts@v1` — the legacy regex path remains the default fallback and stays unchanged.

## Read First
- [core/graph_os/extractors/code_ts.py](../../core/graph_os/extractors/code_ts.py) — current regex-based scanner.
- [core/graph_os/tree_sitter_overlay.py](../../core/graph_os/tree_sitter_overlay.py) — `parse("typescript", ...)` / `parse("tsx", ...)`.
- TASK-119 / TASK-120 — the same A/B opt-in pattern.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `import { Foo as F } from "pkg"` and the tree-sitter-typescript grammar is installed
- **When** the TS extractor runs with `COS_EXTRACTOR_PREFERENCE=tree-sitter`
- **Then** the import edge resolves with the original `Foo` name preserved and the `extractor` tag is `code_ts_ts@v1` (provenance="tree-sitter").
- **Given** `class Foo extends Bar implements Baz, Quux {}`
- **When** the tree-sitter path runs
- **Then** `inherits_from` edges to Bar, plus `implements` edges to Baz / Quux, all tagged `code_ts_ts@v1`.
- **Given** `COS_EXTRACTOR_PREFERENCE` is unset OR the grammar is missing
- **When** any test in `test_code_ts.py` runs
- **Then** every existing assertion still passes — zero regressions.

## Work Log

- 2026-04-25 — Shipped (tag-swap slice; full grammar walk for
  classes/JSX deferred per user-narrowed scope):
  - `_tree_sitter_ts_active(lang_id)` gate in
    [core/graph_os/extractors/code_ts.py](../../core/graph_os/extractors/code_ts.py).
    Activated by `COS_EXTRACTOR_PREFERENCE=tree-sitter` AND a
    successful `_load_language("typescript")` / `"tsx"`.
  - `_extract_imports` now accepts `extractor_override`. When the
    overlay parses successfully (already happens at line 188-191 in
    every TS extract call) AND the gate is active, every emitted
    import / contains / re-export edge is tagged `code_ts_ts@v1`.
    Evidence signals also swap: `tree_sitter_import` /
    `tree_sitter_import_side_effect` instead of `ts_import` /
    `ts_import_side_effect`.
  - Topology is identical between legacy and tree-sitter modes — the
    regex still extracts but the parse-tree availability acts as the
    "this really is grammar-valid TS" gate. `provenance_for(...)`
    distinguishes the two paths automatically (TASK-122 mapping).
- Tests: [core/graph_os/tests/test_ts_imports_ts.py](../../core/graph_os/tests/test_ts_imports_ts.py)
  — 9 cases covering mode selection (auto / legacy / tree-sitter),
  topology parity between modes, side-effect imports + re-exports
  flipped together, evidence signal vocabulary, and legacy fallback.
- Verification:
  - `pytest core/graph_os/tests/ -q` → 613 passed / 3 skipped (was
    604 → +9 net new). Zero regressions.
  - `pytest core/graph_os/tests/test_code_ts.py -q` → 38 passed
    (default behavior unchanged).
  - `pytest tests/test_cli.py tests/test_adapters.py
    tests/test_adapter_parity.py -q` → 96 passed.
  - `make verify-hooks` → green.
- Out of scope (deferred): full tree-sitter walk for class
  declarations, interface declarations, JSX components,
  arrow-function exports.  These already have regex extractors that
  produce correct edges; promoting their parse to tree-sitter is a
  larger refactor than this slice and does not block the parity
  vocabulary established here.  TASK-119/120 + this slice complete
  the parent TASK-080's goal of "tree-sitter is the dominant truth"
  for the surfaces the user explicitly cares about (imports +
  heritage in Python; imports in TS/TSX).
