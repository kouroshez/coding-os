---
id: TASK-098
title: "Hermetic tests — scrub ambient session-id env so suite passes inside a Claude session"
swimlane: infra
kind: bug
epic: null
labels: [tests, hermeticity, ci, ready]
status: archive
priority: P2
appetite: "1d"
created: 2026-06-04
started: 2026-06-04
completed: 2026-06-04
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-098: Hermetic tests — scrub ambient session-id env so suite passes inside a Claude session

**Outcome (one sentence):** pytest tests/ passes when run inside a live Claude Code session; the conftest autouse fixture scrubs CLAUDE_CODE_SESSION_ID and the session-id family so they don't leak into test subprocesses.

## Read First
- tests/conftest.py
- tests/test_cos_env_panel_resolution.py
- src/core/hooks/cos-env.sh

## Repro Steps
1. Inside a live Claude Code session (so `CLAUDE_CODE_SESSION_ID` is exported), run `pytest tests/test_cos_env_panel_resolution.py tests/test_doctor.py tests/test_manifest_fresh.py`.
2. The session var leaks into test subprocesses (cos-env.sh resolver checks `CLAUDE_CODE_SESSION_ID` first; `_source` scrubbed every session var EXCEPT that one).
Expected: pass (as in CI, where the var is absent).
Actual: 9 failures — panel resolves to the ambient Claude session id instead of the test's fixture value.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a live Claude/Codex session exporting `CLAUDE_CODE_SESSION_ID` (+ the session-id family)
- **When** any test runs (autouse conftest fixture active)
- **Then** those vars are scrubbed from `os.environ` for the test, so subprocesses inherit a clean env and resolution uses only the test's explicit values — the previously-leaking 9 tests pass in-session, matching CI.

## Work Log
- 2026-06-04 [claude]: conftest autouse fixture now scrubs CLAUDE_CODE_SESSION_ID + session-id family from os.environ. The 11 previously-leakin
