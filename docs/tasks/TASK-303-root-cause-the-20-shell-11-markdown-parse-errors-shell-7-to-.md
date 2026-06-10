---
id: TASK-303
title: "Root-cause the 20 shell + 11 markdown parse errors (shell 7-to-9, md 8-to-9)"
swimlane: core
kind: bug
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
# TASK-303: Root-cause the 20 shell + 11 markdown parse errors (shell 7-to-9, md 8-to-9)

**Outcome (one sentence):** 34 files carry parse errors (20 .sh via tree-sitter-bash, 11 .md via the link extractor); investigate the real cause per class, fix what is fixable or ensure the fallback recovers the missed symbols, and drive the surfaced parse_error count down materially.

## Read First
- src/core/graph_os/extractors/code_shell.py
- src/core/graph_os/extractors/md_links.py
- src/core/graph_os/tools/graph.py

## Repro Steps
1. `uv run --extra graph_os --extra rag cos graph-reindex --force` → note `parse_errors=N in M files`.
2. Query: `SELECT file_path, parse_errors_count FROM file_index_state WHERE parse_errors_count>0 ORDER BY parse_errors_count DESC`.
3. For a sample .sh and .md, run the extractor directly and inspect the ParseError kind/detail + the tree-sitter ERROR node location.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the 20 .sh parse errors, **When** root-caused, **Then** each is classified (genuine malformed vs extractor/grammar limitation) and the fixable ones are fixed or recovered via the regex fallback, with a test pinning the recovered symbols.
- **Given** the 11 .md parse errors, **When** root-caused, **Then** the link-extractor failures are fixed or shown to be genuinely malformed input (documented), with a regression test.
- **Then** the cumulative parse_error count drops materially from 44, the remaining ones are explained, and graph_os matrix is green.

## Work Log
- 2026-06-10 [claude]: Root-caused 44 parse errors → 3 classes: (1) 28 shell `dynamic` unresolved-source = misclassification (now logger.debug,
- 2026-06-10 [claude]: committed bd20fd21: src/core/graph_os/extractors/code_shell.py, src/core/graph_os/extractors/contracts.py, src/core/grap
