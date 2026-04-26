---
id: TASK-077
title: "Graph: multi-language tree-sitter extractors (TS/JS/Go/Rust/Java parity with the upstream graph tooling)"
swimlane: graph_os
kind: feature
epic: graph_os-the upstream scope-resolution implementation
labels: [hub, graph, parsers, P1-parity]
status: icebox
priority: P1
appetite: "16h"
created: 2026-04-24
started: null
completed: null
agent_session: null
depends_on: [TASK-080]
blocked_by: []
references: []
---

# TASK-077: Graph — multi-language tree-sitter extractors (TS / JS / Go / Rust / Java)

**Outcome (one sentence):** Named bindings, heritage, type annotations, and constructor inference extractors for **TypeScript / JavaScript / Go / Rust / Java** land with full golden-test parity against the external graph tooling capability matrix.

## Read First

- [core/graph_os/tree_sitter_overlay.py](../../core/graph_os/tree_sitter_overlay.py) — the query-bootstrap infra this task extends.
- [core/graph_os/extractors/code_ts.py](../../core/graph_os/extractors/code_ts.py) — TS pattern to mirror for JS/Go/Rust/Java.
- [core/graph_os/extractors/code_python.py](../../core/graph_os/extractors/code_python.py) — heritage + constructor inference reference.
- [docs/engineering/graph_os-queries.md](../../docs/engineering/graph_os-queries.md) — canonical node/edge schema.
- external graph tooling capability matrix (from Phase P1 analysis in session `ad8ed04b`): coding-os currently ≈ 18% of external graph tooling coverage — this task closes most of the gap.

## Priority note

Upgraded from P3 → P1 in the Phase P1 roadmap (session `ad8ed04b`). This is the single biggest parity gap with external graph tooling, and the prerequisite for TASK-074 (Impact UI) being useful on non-Python repos.

## Acceptance (G/W/T) — *this IS the Definition of Done*

For each of the 5 languages (TS, JS, Go, Rust, Java):

- **Given** a language-representative fixture under `core/graph_os/tests/golden/<lang>/`
  **When** `cos graph-reindex --language <lang>` runs
  **Then** the emitted nodes/edges match the recorded golden snapshot byte-for-byte, **and** cover: imports (incl. named bindings & aliasing), class / struct / interface definitions, heritage (extends / implements / embeds / traits), function definitions, method calls, field access, constructor calls.
- **Given** `cos_graph_similar("Foo")` in any of the 5 languages
  **When** the call resolves
  **Then** receiver type inference works across simple assignments and function returns (no self/this → Unknown degradation).
- **Tests:** `core/graph_os/tests/test_extractors_<lang>.py` for each language, collected count ≥ 15 tests per language.
- **Backward compat:** existing Python + TS extractor tests still pass.

## Implementation Notes — per language

**TypeScript / JavaScript** (share parser but different tree-sitter grammars; 2–3 h):
- Reuse `tree-sitter-typescript`; add `tree-sitter-javascript` alongside for `.js` / `.mjs` / `.cjs`.
- JSX handling lands in TS path; keep a dedicated query-set for `jsx_element` + `jsx_self_closing_element` → `DEFINES_COMPONENT` edges.

**Go** (4 h):
- `tree-sitter-go`; extract `package`, `import`, `func`, `type … struct`, `type … interface`, embedding, method receivers (`func (r *Foo) Bar()`).
- Heritage model: structural — emit `STRUCTURAL_IMPLEMENTS` edges when a type has all required methods of an interface (post-pass, not tree-sitter).

**Rust** (3 h):
- `tree-sitter-rust`; extract `mod`, `use`, `struct`, `enum`, `trait`, `impl`, `fn`.
- Heritage: `impl X for Y` → `(Y)-[:IMPLEMENTS]->(X)`. Trait bounds in generics → `REQUIRES_TRAIT`.

**Java** (3 h):
- `tree-sitter-java`; extract `package`, `import`, `class`, `interface`, `extends`, `implements`, `enum`, `record`.
- Annotation processing: emit `ANNOTATED_WITH` edges.

**Integration** (2 h):
- Per-language extractor plugs into the ladder landed by TASK-080.
- Golden fixtures committed as small (≤300 LOC) idiomatic examples covering every edge kind.

## Dependencies

- **Depends on:** TASK-080 (tree-sitter as primary).
- **Unblocks:** TASK-074 Impact UI, TASK-076 Context view, TASK-078 Rename orchestrator — all three become useful only once multi-language indexing exists.

## Work Log
