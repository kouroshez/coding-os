---
id: TASK-293
title: "Surface silent graph parse errors in cos_graph_doctor and reindex summary"
swimlane: core
kind: feature
epic: graph-coverage-hardening
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-09
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260608-203030-6c0f
depends_on: []
blocked_by: []
references: []
---
# TASK-293: Surface silent graph parse errors in cos_graph_doctor and reindex summary

**Outcome (one sentence):** file_index_state.parse_errors_count is collected but invisible (CLI reports "0 errors" = 0 exceptions, hiding ~44 symbol-level parse errors across ~34 files). Surface it in cos_graph_doctor (new files_with_parse_errors category) and the reindex summary so silent-incomplete-coverage stops being silent.

## Read First
- src/core/graph_os/tools/graph.py
- src/core/graph_os/backends/sqlite_backend.py
- src/core/graph_os/tools/reindex_dispatch.py
- docs/engineering/graph_os-queries.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a repo where N files in file_index_state have parse_errors_count > 0, **When** cos_graph_doctor runs, **Then** the envelope data includes a files_with_parse_errors entry reporting the file count and total parse-error count (and a bounded sample list), and the count is non-zero.
- **When** the reindex summary is produced, **Then** it reports files-with-parse-errors / total-parse-errors instead of only exception count, so "errors=0" no longer hides partial extraction.
- **Then** new graph_os tests assert the doctor category and the summary field, and the matrix command `uv run --extra graph_os pytest src/core/graph_os/tests/ -q` is green.

## Work Log
- 2026-06-09 [claude]: Added files_with_parse_errors check to cos_graph_doctor (informational, with per-file sample + parse_error_total stat) a
- 2026-06-09 [claude]: committed 30570b66: src/cli/graph_commands.py, src/core/graph_os/tests/test_centrality_ranking_doctor.py, src/core/graph
