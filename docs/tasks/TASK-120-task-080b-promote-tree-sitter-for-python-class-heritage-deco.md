---
id: TASK-120
title: "TASK-080b: Promote tree-sitter for Python class heritage + decorators"
swimlane: graph_os
kind: refactor
epic: graph_os-graph-tool-parity
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
# TASK-120: TASK-080b: Promote tree-sitter for Python class heritage + decorators

**Outcome (one sentence):** Python class heritage (`class Foo(Bar, Baz):`) and decorator chains (`@app.task @cache.memoize def f():`) are parsed via tree-sitter when active, emitting `inherits_from` and `is_decorated_by` edges tagged `code_python_ts@v1` — the legacy ast path remains the default fallback and stays unchanged.

## Read First
- [core/graph_os/extractors/code_python.py](../../core/graph_os/extractors/code_python.py) — `visit_ClassDef` + `_visit_function` + `decorators_edges` / `inherits` lists.
- [core/graph_os/tree_sitter_overlay.py](../../core/graph_os/tree_sitter_overlay.py).
- TASK-119 — same A/B opt-in pattern (`COS_EXTRACTOR_PREFERENCE=tree-sitter`).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `class Foo(Bar, Baz): ...` and the tree-sitter-python grammar is installed
- **When** the extractor runs with the new tree-sitter primary path
- **Then** two `inherits_from` edges emit (one per parent), each tagged `code_python_ts@v1` so `provenance_for(...)` returns `"tree-sitter"`.
- **Given** chained decorators `@a @b.c def f(): ...`
- **When** the tree-sitter path runs
- **Then** every decorator emits an `is_decorated_by` edge with the same dotted-name semantics as the ast path, tagged `code_python_ts@v1`.
- **Given** the grammar is NOT installed OR `COS_EXTRACTOR_PREFERENCE != "tree-sitter"`
- **When** any test in `test_code_python.py` runs
- **Then** every existing test still passes — zero regressions.

## Work Log

- 2026-04-25 — Shipped:
  - New `_heritage_via_tree_sitter()` + `_decorator_names()` helpers
    in [core/graph_os/extractors/code_python.py](../../core/graph_os/extractors/code_python.py).
    Walks the tree-sitter Python AST and returns the same
    `(class_uid, base_name)` and `(decorated_uid, dec_name)` tuple
    shape that `_PythonVisitor` builds during ast traversal — so the
    emission code is unchanged and edge counts stay identical.
  - Activation: same `_tree_sitter_imports_active()` gate as TASK-119
    (single `--extractor=tree-sitter` flag flips both paths in
    lock-step).
  - When active, `visitor.inherits` and `visitor.decorators_edges`
    are replaced with the tree-sitter output and `inherits_from` /
    `is_decorated_by` edges are emitted with `extractor=
    code_python_ts@v1` so `provenance_for(...)` returns
    `"tree-sitter"`.
  - Evidence signals also swap: `tree_sitter_base_class` /
    `tree_sitter_decorator` instead of the ast variants.
  - Nested-scope qualnames preserved: `class Outer: class Inner:` →
    `code:class:foo.py::Outer.Inner`.
  - Decorator-with-args (`@memoize(ttl=60)`) strips the call to keep
    the dotted name only — matches `_dotted_name(ast.Call)` semantics.
- Tests: [core/graph_os/tests/test_python_heritage_ts.py](../../core/graph_os/tests/test_python_heritage_ts.py)
  — 15 cases covering mode selection (auto / legacy / tree-sitter),
  multi-base inheritance, dotted bases, chained decorators, dotted
  decorators, decorator-with-call-args, decorator on a class,
  nested-class qualnames, ast/tree-sitter topology parity for
  `inherits_from` and `is_decorated_by`, and the new
  `tree_sitter_base_class` / `tree_sitter_decorator` evidence
  signals.
- Verification:
  - `pytest core/graph_os/tests/ -q` → 604 passed / 3 skipped (was
    589 → +15 net new). Zero regressions.
  - `pytest core/graph_os/tests/test_code_python.py
    core/graph_os/tests/test_python_imports_ts.py -q` → 50 passed
    (39 default + 11 tree-sitter-imports).
  - `pytest tests/test_cli.py tests/test_adapters.py
    tests/test_adapter_parity.py -q` → 96 passed.
  - `make verify-hooks` → green.
