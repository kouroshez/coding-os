---
id: TASK-083
title: "graph_os P1: Type annotations extractor (function params, return types, class fields) for receiver resolution"
swimlane: graph_os
kind: feature
epic: graph_os-graph-tool-parity
labels: [hub, graph, types, P1-parity]
status: icebox
priority: P1
appetite: "6h"
created: 2026-04-24
started: null
completed: null
agent_session: null
depends_on: [TASK-080]
blocked_by: []
references: []
---

# TASK-083: graph_os P1 — Type annotations extractor

**Outcome (one sentence):** `cos_graph_similar` and call-site resolution pass `self` / `this` through annotated types; `def f(x: Foo) -> Bar` emits `HAS_PARAM_TYPE`, `RETURNS_TYPE`, and field-access edges with confidence ≥ 0.9, closing the "Type Annotations — " gap in the graph-tool parity matrix.

## Read First

- [core/graph_os/extractors/code_python.py](../../core/graph_os/extractors/code_python.py) — current Python extractor that already visits function definitions but throws away annotations.
- [core/graph_os/extractors/code_ts.py](../../core/graph_os/extractors/code_ts.py) — TS counterpart; its type grammar is more involved (generics, unions, mapped).
- [core/graph_os/types.py](../../core/graph_os/types.py) — `EdgeKind`; add `HAS_PARAM_TYPE`, `RETURNS_TYPE`, `FIELD_OF_TYPE` enums.
- [docs/engineering/graph_os-queries.md](../../docs/engineering/graph_os-queries.md) — update schema table at the end.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** a Python file:
  ```python
  class Foo:
      name: str = ""
      def greet(self) -> str: return f"hi {self.name}"

  def welcome(x: Foo) -> str: return x.greet()
  ```
  **When** extraction runs
  **Then** edges exist: `(welcome)-[:HAS_PARAM_TYPE {confidence:0.95}]->(Foo)`, `(welcome)-[:RETURNS_TYPE]->(str)`, `(Foo.name)-[:FIELD_OF_TYPE]->(str)`, and `(welcome.body:x.greet)-[:CALLS {via:param-type-inference}]->(Foo.greet)`.
- **Given** a TS file `function welcome(x: Foo): string { return x.greet(); }`
  **When** extraction runs
  **Then** the same three edge kinds land with identical confidence budgeting.
- **Given** a type that cannot be resolved (`x: SomeThirdPartyType`)
  **When** extraction runs
  **Then** the edge emits with `confidence: 0.3` and `target: unresolved:SomeThirdPartyType` — preserved, not dropped.
- **Given** `cos_graph_similar("Foo")` called with attribute-chain context
  **When** the tool resolves `x.greet()`
  **Then** `x` is typed as `Foo` via the `HAS_PARAM_TYPE` edge and the call correctly routes to `Foo.greet`.
- **Tests:** `core/graph_os/tests/test_type_annotations.py` with ≥ 10 assertions per language (Python + TS).

## Implementation Notes

1. **Python:** re-use `ast.AnnAssign` / `ast.FunctionDef.args[*].annotation` / `.returns` — they already exist, we just need to emit edges. For `Union[X, Y]` / `X | Y` emit two edges (one per branch) with `confidence/num_branches`.
2. **TS:** tree-sitter `type_annotation` node already available post TASK-080; extract `type_identifier`, `generic_type`, `union_type`, `intersection_type`. Generics without resolvable bound → `unresolved:T`.
3. **Storage:** add a fourth column `confidence` to the edges table (if not already present in migration v19 — verify before touching schema, append-only rule applies).
4. **Call-site resolution pass:** after all extractors, a `receiver_resolver.py` second pass walks call sites whose receiver is a variable name, looks up the surrounding scope, and follows the most recent `HAS_PARAM_TYPE` / assignment → `TypeInferred` binding.
5. Keep `lsp_overlay` as higher-confidence refinement — when LSP agrees with annotation it stays 0.95; when LSP disagrees, prefer LSP and record `source: "lsp-override"`.

## Dependencies

- **Depends on:** TASK-080 (need tree-sitter TS type grammar; Python can start earlier but easier to batch).
- **Unblocks:** TASK-075 (process-grouped search), TASK-076 (Context view — shows outgoing calls with resolved targets).

## Work Log
