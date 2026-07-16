---
id: TASK-296
title: "Polyglot graph coverage: generic tree-sitter extractor + expanded language INCLUDE"
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
# TASK-296: Polyglot graph coverage: generic tree-sitter extractor + expanded language INCLUDE

**Outcome (one sentence):** DEFAULT_INCLUDE covers only shipped stacks, so an enterprise polyglot repo (Java/Rust/Ruby/C#/SQL) gets zero code graph; add a generic tree-sitter extractor that pulls functions/classes/calls from ANY installed grammar at a baseline and expand DEFAULT_INCLUDE so the long tail is bounded by one extractor rather than N hand-written ones.

## Read First
- src/core/graph_os/ingest/base.py
- src/core/graph_os/extractors
- src/core/graph_os/types.py
- docs/playbooks/polyglot-extractor-roadmap.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a source file in a language with an installed tree-sitter grammar but no hand-written extractor (e.g. .rs/.java/.rb), **When** the file is indexed, **Then** the generic extractor emits stable-uid nodes for its top-level functions/classes and contains edges, idempotent on re-extraction.
- **Given** no grammar is installed for an extension, **When** indexing runs, **Then** the extractor fails open (file skipped, recorded as parse error per TASK-293, no crash) and existing hand-written extractors (py/ts/go/php/sh) still take precedence over the generic one.
- **Then** DEFAULT_INCLUDE is expanded for the supported long-tail extensions, a graph_os test proves a generic-language file yields nodes, and the matrix command `uv run --extra graph_os pytest src/core/graph_os/tests/ -q` is green.

## Work Log
- 2026-06-09 [claude]: Added code_generic: one table-driven tree-sitter extractor emitting file+folder-spine+function/class+contains for any gr
- 2026-06-09 [claude]: committed 720feb0f: docs/engineering/graph_os-queries.md, docs/playbooks/polyglot-extractor-roadmap.md, pyproject.toml, 
