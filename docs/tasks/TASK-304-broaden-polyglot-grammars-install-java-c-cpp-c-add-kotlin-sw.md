---
id: TASK-304
title: "Broaden polyglot grammars: install java/c/cpp/c#, add kotlin/swift/scala/sql/lua rows"
swimlane: core
kind: feature
epic: graph-coverage-hardening
labels: [ready]
status: complete
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
# TASK-304: Broaden polyglot grammars: install java/c/cpp/c#, add kotlin/swift/scala/sql/lua rows

**Outcome (one sentence):** code_generic is code-ready for java/c/cpp/c# but their grammars are not installed, and kotlin/swift/scala/sql/lua have no _LANG_SPEC row; install the missing grammars, add overlay loaders + verified node-type rows + EXT_MAP routes + DEFAULT_INCLUDE entries, each proven by a test against the real installed grammar.

## Read First
- src/core/graph_os/extractors/code_generic.py
- src/core/graph_os/tree_sitter_overlay.py
- src/core/graph_os/tools/reindex_dispatch.py
- src/core/graph_os/ingest/base.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** java/c/cpp/c# are code-ready but grammar-less, **When** their grammars are added to the graph_os extra, **Then** a real source sample in each yields function/class nodes via code_generic (node types verified against the installed grammar, not guessed).
- **Given** kotlin/swift/scala/sql/lua have no spec, **When** rows + loaders + routes + INCLUDE entries are added (only for grammars that actually install + import cleanly), **Then** each added language extracts nodes in a test; any grammar that won't install is left out with a note (no dead row).
- **Then** unsupported/uninstalled extensions still fail open (file node + parse error), hand-written extractors keep precedence, docs list the new languages, and graph_os matrix is green.

## Work Log
- 2026-06-10 [claude]: Shipped grammars for java/c/cpp/c#/scala/kotlin/lua (all verified to load with core 0.25); added overlay loaders + _LANG
- 2026-06-10 [claude]: committed ec1550e1: docs/engineering/graph_os-queries.md, docs/playbooks/polyglot-extractor-roadmap.md, pyproject.toml, 
