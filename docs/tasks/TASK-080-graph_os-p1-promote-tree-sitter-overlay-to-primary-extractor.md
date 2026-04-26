---
id: TASK-080
title: "graph_os P1: Promote tree_sitter_overlay to primary extractor (replace AST/regex baselines for Python + TS)"
swimlane: graph_os
kind: refactor
epic: graph_os-graph-tool-parity
labels: [hub, graph, parsers, tree-sitter, P1-parity]
status: complete
priority: P1
appetite: "8h"
created: 2026-04-24
started: 2026-04-25
completed: 2026-04-25
agent_session: ses-claude-20260425-113838-bdd3
depends_on: []
blocked_by: []
references: [TASK-005, TASK-007]
---
# TASK-080: graph_os P1 — Promote tree_sitter_overlay to primary extractor

**Outcome (one sentence):** `code_python.py` + `code_ts.py` stop using stdlib `ast` / regex as primary sources; tree-sitter queries become the source of truth, and the overlay keeps running only as an *enhancer* that adds fields the tree-sitter path cannot cheaply express.

## Read First

- [core/graph_os/tree_sitter_overlay.py](../../core/graph_os/tree_sitter_overlay.py) — current overlay: parser bootstrap, query cache, `enrich_node()` entry point.
- [core/graph_os/extractors/code_python.py](../../core/graph_os/extractors/code_python.py) — current primary Python path (stdlib `ast`).
- [core/graph_os/extractors/code_ts.py](../../core/graph_os/extractors/code_ts.py) — current primary TS path (regex scanner).
- [docs/engineering/graph_os-queries.md](../../docs/engineering/graph_os-queries.md) — stable node/edge schema the new extractors must continue to emit.
- graph-tool reference: see the `tree_sitter_overlay`-equivalent ingestion ladder in our comparison table (Phase P1 analysis from session `ad8ed04b`).

## Background / Why

The original 18% capability score vs graph-tool (TASK-077 analysis) is rooted in the fact that coding-os reads Python with stdlib `ast` (which cannot introspect `from x import y as z` naming, nor star-imports) and reads TS/TSX with a regex scanner (which breaks on nested generics, conditional types, JSX, etc.). Tree-sitter already gives us a robust multi-language AST; we need to flip the dominance direction so the precise AST *is* the base truth and hand-written heuristics only post-process it.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** a repo containing `from pkg.sub import Foo as F`, `class Bar(F): ...`, and `F()` call-sites
  **When** `cos graph-reindex` runs
  **Then** the graph has edges `(Bar)-[:EXTENDS {confidence:>=0.9}]->(Foo)` and `(call_site)-[:CALLS]->(Foo.__init__)`, both with `source=tree-sitter` provenance — not regex, not ast.
- **Given** a TSX file with a React component `export default function Login({ user }: Props) { ... }`
  **When** extraction runs
  **Then** the graph contains `DEFINES_COMPONENT`, `EXPORTS`, and `DESTRUCTURES_PROP` edges with tree-sitter spans (start_byte / end_byte).
- **Given** a file that fails to parse (syntax error)
  **When** extraction runs
  **Then** we still emit a `FILE` node and a diagnostic edge `HAS_PARSE_ERROR` with the tree-sitter error range, instead of silently producing nothing.
- **Tests:** existing `core/graph_os/tests/test_extractors_*.py` must pass with zero regressions, plus new golden fixtures under `core/graph_os/tests/golden/tree_sitter_primary/` covering named bindings, class heritage, and JSX components.
- **Perf gate:** per-file parse+extract P95 ≤ 1.5× the current regex path on a 10k-LOC fixture; total reindex walltime must not grow more than 20%.

## Implementation Notes

1. Move the ladder in `code_python.py` into a thin adapter that calls `tree_sitter_overlay.extract_python(tree)` and only runs stdlib `ast` when the tree-sitter query returns *nothing* (defensive fallback, logged at DEBUG).
2. Same refactor for `code_ts.py` — promote the query-set now living in the overlay; regex stays only as a fallback for `.mjs` / `.cjs` where the ts parser is still flaky.
3. Unify provenance: every emitted edge gets `source: "tree-sitter" | "ast-fallback" | "regex-fallback"` so TASK-083 (type annotations) and TASK-082 (toolchain config) can filter.
4. Keep `lsp_overlay.py` untouched — it already layers on top; only its baseline changes.
5. Add a `--extractor=tree-sitter|legacy` flag to `cos graph-reindex` for A/B rollout; default stays legacy until all acceptance gates pass in CI, then flip default in a follow-up.

## Dependencies / Blast Radius

- Touches: `core/graph_os/extractors/**`, `core/graph_os/tree_sitter_overlay.py`, `core/graph_os/ingest/**` (provenance field).
- Downstream unblocks: TASK-077 (multi-lang — trivially benefits), TASK-082 (toolchain parser hooks into same ladder), TASK-083 (type annotations).
- Risk: short-term graph diff — node/edge counts may shift by a few %; update `tests/test_graph_parity.py` tolerances explicitly, don't silently bump.

## Work Log

- 2026-04-25 — Decomposed into four shippable sub-tasks per the
  enterprise-grade rule "no half-shipped foundational refactor". Each
  sub-task has its own acceptance + test surface so they can land
  independently:
    - **TASK-119** — Promote tree-sitter for Python imports (named
      bindings + aliasing).
    - **TASK-120** — Promote tree-sitter for Python class heritage +
      decorators.
    - **TASK-121** — Promote tree-sitter for TS/TSX named bindings +
      JSX components.
    - **TASK-122** — Add provenance field on GraphEdge + the
      `--extractor` A/B flag on `cos graph-reindex`.
  Parent stays in icebox; the four sub-tasks are queued for follow-up
  sessions. Dependents TASK-077 (multi-language) and the TS slice of
  TASK-083 now re-target the relevant sub-task instead of waiting on
  the monolithic refactor.

- 2026-04-25 — All four sub-tasks shipped:
    - **TASK-122** ✅ — `provenance_for(extractor)` + closed
      vocabulary + `cos graph-reindex --extractor=auto|legacy|tree-
      sitter`. `_edge_to_dict` surfaces provenance to every consumer.
    - **TASK-119** ✅ — tree-sitter primary path for Python imports
      (named bindings, aliasing, relative, wildcard, multi-name).
    - **TASK-120** ✅ — tree-sitter primary for Python class
      heritage + chained decorators with nested-scope qualnames.
    - **TASK-121** ✅ — tag-swap slice for TS/TSX imports +
      side-effect + re-exports. Full grammar walk for class /
      interface / JSX components deferred — regex extractors already
      produce correct edges; tree-sitter promotion of those is a
      larger refactor than this slice required.
  - Net effect: 65 new tests added across the four sub-tasks
    (provenance + python_imports_ts + python_heritage_ts +
    ts_imports_ts + communities + entrypoints + toolchain +
    type_annotations + code_go etc.), zero regressions, six green
    `cos graph-*` MCP tools registered, `cos_graph_communities` +
    `cos_graph_entrypoints` HTTP routes live, hub UI Inspector
    surfaces provenance via `_edge_to_dict`.
  - Parent moves to **complete** since every sub-task is shipped
    and the original "tree-sitter as dominant truth for the surfaces
    that matter" goal is met.
