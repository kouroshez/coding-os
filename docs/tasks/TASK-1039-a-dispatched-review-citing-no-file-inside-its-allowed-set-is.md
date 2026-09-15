---
id: TASK-1039
title: "A dispatched review citing no file inside its allowed set is accepted"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-09-15
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1039: A dispatched review citing no file inside its allowed set is accepted

**Outcome (one sentence):** A cross-provider review that never touched the files it was dispatched for is rejected instead of recorded as a completed review.

## Read First
- src/core/hooks/_helpers/auto_dispatch.py
- src/core/thinking_os/tools/_dispatch_request.py
- src/core/hooks/_helpers/dispatch_summary.py

TASK-1031 stopped a child inheriting another session's task, which removes the
cause of the observed wrong-subsystem audit. This is the independent check on the
same failure: validate where the finished review actually looked.

Raised on r/ChatGPTCoding (2026-09-14). The reviewer is dispatched for a known set
of paths. If its output cites no path inside that set, the run did not review what
it was paid to review, whatever produced the mismatch. The wrong-subsystem run
would have failed this on its first cited file.

Worth having even though TASK-1031 is fixed, because it does not depend on the
scope being resolved correctly: it checks the result rather than the input, so it
catches a drift no input-side guard can see.


## Repro Steps
1. `python3 -c "import sqlite3,os; c=sqlite3.connect(os.environ['COS_DB_PATH']).cursor(); print(c.execute('SELECT id,task_marker,persona_id,raw_transcript FROM formula_dispatches WHERE id=63').fetchone()[:3])"` — row 63 is the observed case.
2. Read its `raw_transcript`: the agent states it is scoped to `src/core/graph_os`, while `task_marker` is TASK-1029, whose diff is a single file under `tests/`.
3. The row's `status` is `ok` and its `cost_usd` is 1.352399. Nothing recorded that the cited paths and the dispatched scope never intersected.
2. ...
Expected: ...
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a completed dispatch whose cited paths do not intersect its allowed set
  **When** the result is recorded
  **Then** it is marked invalid with the cited and allowed sets named, and does not count as a review the card can move on.
- **Given** a completed dispatch citing at least one allowed path
  **When** the result is recorded
  **Then** it is recorded normally.
- **Given** a dispatch that cites no paths at all
  **When** the result is recorded
  **Then** it is marked invalid for the same reason rather than passing by vacuous truth.

## Work Log
