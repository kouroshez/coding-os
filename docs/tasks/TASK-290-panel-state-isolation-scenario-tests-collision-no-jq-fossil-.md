---
id: TASK-290
title: "Panel-state isolation scenario tests (collision / no-jq / fossil / multi-adapter)"
swimlane: core
kind: test
epic: panel-state-isolation
labels: [state-isolation, tests, concurrency, ci-guard, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-09
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260609-143642-c7c5
depends_on: [TASK-287, TASK-288]
blocked_by: []
references: []
---
# TASK-290: Panel-state isolation scenario tests (collision / no-jq / fossil / multi-adapter)

**Outcome (one sentence):** Scenario tests under controlled env that prove the B-epic hardening. Improve the existing tests (test_cos_env_panel_resolution.py, test_inject_mcp_caller_session.py, test_agent_presence_state.py, test_hooks_fail_closed.py) — do NOT duplicate. Cover: (a) runtime session-id present -> two panels isolated; (b) session-id absent + same PPID -> collision DETECTED and a loud warning/diagnostic emitted (not silent); (c) jq absent -> inject hook fails LOUD not exit-0; (d) sibling fossil in agent-dir -> rejected on session mismatch; (e) Claude+Codex multi-adapter -> isolated dirs. Structured assertions + progress output.

## Read First
- tests/test_cos_env_panel_resolution.py
- tests/test_inject_mcp_caller_session.py
- tests/test_hooks_fail_closed.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the B-epic hardening has landed (TASK-287 jq fail-closed + WIP detection, TASK-288 ppid detector + session-validated fallbacks).
- **When** the scenario suite runs the five cases under controlled env (session-id present; session-id absent + same PPID; jq absent; sibling fossil; Claude+Codex multi-adapter).
- **Then** each case asserts the intended behavior — two panels isolated; collision DETECTED + warned (not silent); inject hook fails LOUD not exit-0; sibling fossil rejected on session mismatch; multi-adapter dirs isolated — existing tests are improved (not duplicated), with structured assertions + progress output, green under `uv run pytest`.

## Work Log
- 2026-06-09 [claude]: Improved existing tests (no duplication): +7 scenarios in test_cos_env_panel_resolution.py [(a) two sessions isolate pan
