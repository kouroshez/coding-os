---
id: TASK-119
title: "TASK-080a: Promote tree-sitter for Python imports (named bindings + aliasing)"
swimlane: graph_os
kind: refactor
epic: graph_os-the upstream scope-resolution implementation
labels: []
status: complete
priority: P2
appetite: "1d"
created: 2026-04-25
started: 2026-04-25
completed: 2026-04-25
agent_session: null
depends_on: []
blocked_by: []
references: []
---
# TASK-119: TASK-080a: Promote tree-sitter for Python imports (named bindings + aliasing)

**Outcome (one sentence):** Python `from pkg.sub import Foo as F` is parsed via tree-sitter (when the grammar is installed) so `F` resolves to the original `pkg.sub.Foo` and emits the `import` edge tagged `provenance="tree-sitter"` — keeping the existing stdlib `ast` path as a guaranteed fallback for hosts without the grammar.

## Read First
- [core/graph_os/extractors/code_python.py](../../core/graph_os/extractors/code_python.py) — current ast-based import resolver.
- [core/graph_os/tree_sitter_overlay.py](../../core/graph_os/tree_sitter_overlay.py) — `parse(language_id, content)` returns `OverlayParse(tree, root)` or None.
- [core/graph_os/types.py](../../core/graph_os/types.py) — `provenance_for("code_python_ts@v1")` already maps to `tree-sitter` (TASK-122).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `from pkg.sub import Foo as F` and the tree-sitter-python grammar is installed
- **When** the extractor runs with the new tree-sitter primary path
- **Then** the import edge resolves to a target uid containing the original `pkg.sub:Foo` name (not the alias `F`) and the edge's `extractor` tag is `code_python_ts@v1` so `provenance_for(...)` returns `"tree-sitter"`.
- **Given** a host where the grammar is NOT installed
- **When** the same file is processed
- **Then** the existing ast path produces identical edges with `extractor="code_python@v1"` (provenance=`ast`) — zero regressions in `test_code_python.py`.
- **Given** wildcard imports (`from pkg import *`) and complex aliasing chains
- **When** the tree-sitter path runs
- **Then** the existing ast wildcard / chain semantics are preserved — same edges, just different provenance tag.

## Work Log

- 2026-04-25 — Shipped:
  - New `_imports_via_tree_sitter()` + `_emit_import_statement` /
    `_emit_import_from` helpers in
    [core/graph_os/extractors/code_python.py](../../core/graph_os/extractors/code_python.py).
    Walks the tree-sitter Python AST to populate the same
    `_ImportDecl` shape the ast visitor produces — alias preservation,
    relative imports, wildcard, multi-name `from X import a, b`.
  - `_tree_sitter_imports_active()` gate: opt-in via
    `COS_EXTRACTOR_PREFERENCE=tree-sitter` (set by
    `cos graph-reindex --extractor=tree-sitter` from TASK-122). When
    inactive (default `auto`) the legacy ast path runs unchanged.
  - When active AND the grammar parse succeeds, `visitor.imports` and
    `visitor.imported_local_names` are replaced with the tree-sitter
    output and the import-edge `extractor` tag flips to
    `code_python_ts@v1`. `provenance_for(...)` returns
    `"tree-sitter"` automatically (TASK-122 mapping).
  - Evidence signal also swaps: `tree_sitter_import` instead of
    `ast_import` so downstream consumers can audit.
- Tests: [core/graph_os/tests/test_python_imports_ts.py](../../core/graph_os/tests/test_python_imports_ts.py)
  — 11 cases covering mode selection (auto / legacy / tree-sitter),
  simple + aliased + from-imports + wildcard + multi-name imports,
  topology parity between ast and tree-sitter modes, and
  evidence-signal vocabulary.
- Verification:
  - `pytest core/graph_os/tests/ -q` → 589 passed / 3 skipped (was
    578 → +11 net new). Zero regressions.
  - `pytest core/graph_os/tests/test_code_python.py -q` → 39 passed
    in default mode (legacy ast path unchanged).
  - `pytest tests/test_cli.py tests/test_adapters.py
    tests/test_adapter_parity.py -q` → 96 passed.
  - `make verify-hooks` → green.
  - End-to-end smoke: `COS_EXTRACTOR_PREFERENCE=tree-sitter` on a
    file with 5 import statements (alias, relative, wildcard,
    multi-name) → 6 import edges all tagged `code_python_ts@v1`.
- Out of scope: tree-sitter primary path for class heritage +
  decorators (TASK-120) and TS/TSX (TASK-121) — same dispatch
  pattern, separate sub-tasks.
