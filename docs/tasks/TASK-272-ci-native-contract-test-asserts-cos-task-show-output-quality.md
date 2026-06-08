---
id: TASK-272
title: "CI-native contract test asserts cos_task_show output quality"
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
# TASK-272: CI-native contract test asserts cos_task_show output quality

**Outcome (one sentence):** A pytest contract test in the board_os matrix asserts cos_task_show returns its full field set + ok/fail envelope + meta.layer, so MCP output quality is measured in CI and a dropped field fails the build.

## Read First
- src/core/board_os/tests/test_mcp_tools.py — fixtures + cos_task_show tests
- src/core/board_os/mcp_tools.py — cos_task_show (~968)
- src/scripts/audit_mcp_tools.py — existing manual all-tool audit

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the board_os test matrix, **When** it runs, **Then** test_task_show_returns_full_field_contract asserts the ok envelope, the full required field set (incl. epic/labels/agent_session/started_at/completed_at), and meta.layer=='tasks'.
- **Given** a future refactor that drops a cos_task_show field, **When** the suite runs, **Then** the contract test fails (set-difference assertion names the missing field).
- **Given** a missing task id, **When** cos_task_show is called, **Then** a fail envelope with category not_found is asserted.

## Work Log
- 2026-06-08 [claude]: Added test_task_show_returns_full_field_contract + test_task_show_not_found_returns_fail_envelope to board_os/tests/test
