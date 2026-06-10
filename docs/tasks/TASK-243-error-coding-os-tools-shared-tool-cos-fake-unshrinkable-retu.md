---
id: TASK-243
title: "[error] coding_os.tools._shared: tool cos_fake_unshrinkable returned an unshrinkable envelope"
swimlane: infra
kind: bug
epic: null
labels: [fp:edfe4f913e54279b, auto-error, error-sweep, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-07
started: null
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-243: [error] coding_os.tools._shared: tool cos_fake_unshrinkable returned an unshrinkable envelope

**Outcome (one sentence):** Recurring ERROR from coding_os.tools._shared (count=4, sessions=0, exc=None). First 2026-06-06T14:43:59Z, last 2026-06-07T17:33:06Z. Investigate: cos errors --scope coding_os.tools._shared

## Read First
- (no doc yet — exploratory)

## Repro Steps
1. (fill in: exact steps to reproduce)
2. ...
Expected: ...
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
- 2026-06-08 [claude]: Phantom task — root cause is test-fixture noise, not a real bug. `cos_fake_unshrinkable` is a pytest fixture in `src/core/thinking_os/tests/test_envelope.py::TestSafeToolNamesUnshrinkable` that deliberately triggers `safe_tool`'s unshrinkable-envelope ERROR log; the old error-sweep filed that log line as a recurring production error. Fixed in commit 0db38436: `select_for_filing` now skips session-less non-FATAL fingerprints, and `thinking_os/tests/conftest.py` isolates `COS_DB_PATH` so error-path fixtures never reach the durable store. Archived.
