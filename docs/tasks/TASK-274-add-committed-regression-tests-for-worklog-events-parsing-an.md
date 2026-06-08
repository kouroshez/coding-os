---
id: TASK-274
title: "Add committed regression tests for worklog-events parsing and Read First dead-link check"
swimlane: core
kind: test
epic: hub-redesign
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-618-2ab7
depends_on: []
blocked_by: []
references: []
---
# TASK-274: Add committed regression tests for worklog-events parsing and Read First dead-link check

**Outcome (one sentence):** _worklog_events (C3a) and _read_first_missing_paths (C5a) gain committed unit tests so a future refactor that breaks worklog-timeline parsing or the dead-link gate fails the build instead of silently regressing.

## Read First
- src/core/board_os/tests/test_mcp_tools.py — fixtures (project, conn)
- src/core/board_os/tests/test_transition_gates_validator.py — validator tests
- src/core/board_os/mcp_tools.py — _worklog_events
- src/core/board_os/transition_gates_validator.py — _read_first_missing_paths

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a task file with Work Log bullets, **When** _worklog_events parses it, **Then** each bullet becomes a dated, actor-attributed worklog event in file order; a non-bullet/garbage line is ignored.
- **Given** Read First text with a real path, a missing repo path, a URL and a glob, **When** _read_first_missing_paths runs against a root, **Then** only the missing repo path is returned (URL/glob/real-path excluded).
- **Given** the board_os matrix run, **When** it executes, **Then** both new tests pass alongside the existing suite.

## Work Log
- 2026-06-08 [claude]: Added 4 regression tests: _read_first_missing_paths (flags only dead repo paths; skips URL/glob/real/prose) + dead-link-
