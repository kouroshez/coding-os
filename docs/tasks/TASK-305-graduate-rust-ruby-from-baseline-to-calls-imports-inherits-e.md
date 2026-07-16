---
id: TASK-305
title: "Graduate Rust + Ruby from baseline to calls/imports/inherits edges"
swimlane: core
kind: feature
epic: graph-coverage-hardening
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-09
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260608-203030-6c0f
depends_on: []
blocked_by: []
references: []
---
# TASK-305: Graduate Rust + Ruby from baseline to calls/imports/inherits edges

**Outcome (one sentence):** code_generic gives Rust/Ruby only file+spine+function/class+contains (completeness ~5); add per-language calls, imports (rust use, ruby require/require_relative), and inheritance edges (rust impl-of-trait, ruby superclass/include) following the code_go pattern, so both reach Go-grade completeness (~8) with honest confidence tiers.

## Read First
- src/core/graph_os/extractors/code_generic.py
- src/core/graph_os/extractors/code_go.py
- src/core/graph_os/types.py
- src/core/graph_os/tree_sitter_overlay.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a Rust file with `use` imports, function calls, and `impl Trait for Type`, **When** indexed, **Then** the graph has import edges, calls edges (AST-confidence tiered), and an inherits/implements edge — beyond the baseline contains.
- **Given** a Ruby file with require/require_relative, method calls, class superclass and include, **When** indexed, **Then** the graph has the corresponding import, calls, and inherits edges.
- **Given** confidence calibration (graph-os-authoring §3), **When** edges are emitted, **Then** AST-direct calls are high-confidence and ambiguous same-name dispatch is tiered lower, never inflated. Decide whether this lives in code_generic (per-lang hooks) or dedicated code_rust/code_ruby modules and record the choice.
- **Then** new tests assert each edge kind for both languages; existing baseline tests stay green; graph_os matrix green; docs/score table updated (Rust/Ruby completeness 5→~8).

## Work Log
- 2026-06-10 [claude]: Added per-language edge hooks in code_generic (decision: hooks over separate modules — shared node baseline, only edge g
- 2026-06-10 [claude]: committed 28339df3: docs/engineering/graph_os-queries.md, docs/playbooks/polyglot-extractor-roadmap.md, src/core/graph_o
