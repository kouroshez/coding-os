---
id: TASK-1058
title: "Green the nightly: the task-start smoke test inherits the conftest COS_STATE_DIR"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-10-09
started: 2026-10-08
completed: 2026-10-08
agent_session: ses-claude-20261004-231430-d18a
depends_on: []
blocked_by: []
references: []
---
# TASK-1058: Green the nightly: the task-start smoke test inherits the conftest COS_STATE_DIR

**Outcome (one sentence):** test_task_start_blocks_template_placeholder_outcome passes again because its CLI subprocesses use the project's own .coding-os, so the nightly slow suite stops failing on it.

## Read First
- tests/conftest.py
- tests/test_rag_pipeline.py

## Repro Steps
1. `uv run --extra rag pytest "tests/test_rag_pipeline.py::test_task_start_blocks_template_placeholder_outcome" -q`
2. Its `task-create` subprocess inherits the `COS_STATE_DIR` that conftest points at `pytest-N/state0`.
Expected: the task is created in the scaffolded project's DB.
Actual: `DB not found at pytest-N/.coding-os/coding-os.db`; the nightly has failed on it every day since at least 2026-10-01.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the nightly slow suite
- **When** `test_task_start_blocks_template_placeholder_outcome` runs alone or with its file
- **Then** it passes and its `task-create` reaches the project's own DB

## Work Log
- 2026-10-09 [claude]: commit fb2ec0a446 — test: give the task-start smoke its project's state dir so the nightly slow suite passes
- 2026-10-09 [claude]: Status transitioned to complete via cos task-done.
