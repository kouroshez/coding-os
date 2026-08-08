---
id: TASK-917
title: "Split tests/test_cli.py into _cli_suite part modules behind the aggregator"
swimlane: cli
kind: refactor
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-08
started: 2026-08-08
completed: 2026-08-08
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-917: Split tests/test_cli.py into _cli_suite part modules behind the aggregator

**Outcome (one sentence):** tests/test_cli.py drops from 5652 to an aggregator (<200 lines) importing part modules; all 281 tests still collect and pass under the unchanged node ids tests/test_cli.py::*.

## Read First
- tests/test_cli.py
- src/core/graph_os/tools/graph.py
- tests/test_file_size_budget.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the split into _cli_suite part modules
  **When** `uv run pytest tests/test_cli.py -q` runs
  **Then** all 281 tests collect and pass
- **Given** external node-id references
  **When** `tests/test_cli.py::TestCosPr` / `::TestSubsystems` are selected
  **Then** they still run
- **Given** the file-size ratchet
  **When** `tests/test_file_size_budget.py` runs
  **Then** it passes with a lowered MAX_LINES

## Work Log
- 2026-08-08 [claude]: Edit split_test_cli.py
- 2026-08-08 [claude]: Edit pr.py
- 2026-08-08 [claude]: Edit split_mcp_tools.py
- 2026-08-08 [claude]: Edit pyproject.toml
- 2026-08-08 [claude]: Edit split_doctor.py
- 2026-08-08 [claude]: Edit pyproject.toml
- 2026-08-08 [claude]: Edit pyproject.toml
- 2026-08-08 [claude]: Edit test_file_size_budget.py
- 2026-08-08 [claude]: Edit test_cli.py
- 2026-08-08 [claude]: Edit mcp_tools.py
- 2026-08-08 [claude]: Edit fix_mcp_cycle.py
- 2026-08-08 [claude]: Edit git_probe.py
- 2026-08-08 [claude]: Status transitioned to complete via cos task-done.
