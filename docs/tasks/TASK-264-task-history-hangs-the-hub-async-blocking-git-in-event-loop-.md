---
id: TASK-264
title: "Task history hangs the hub \u2014 async-blocking git in event loop + date-as-SHA false match"
swimlane: core
kind: bug
epic: hub-redesign
labels: [ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-618-2ab7
depends_on: []
blocked_by: []
references: []
---
# TASK-264: Task history hangs the hub — async-blocking git in event loop + date-as-SHA false match

**Outcome (one sentence):** Opening a task in the hub loads history fast and never shows wrong commits — git work runs off the event loop and only real commit SHAs (not session-id dates) are resolved.

## Read First
- src/core/board_os/mcp_tools.py — _git_commits_from_worklog (~2228), cos_task_history (~2274)
- src/core/web/routes/board.py — board_task_history (~541), board_task_detail (~168), board_list (~275)
- src/core/web/ui/src/lib/api-client.ts — fetch wrapper (no timeout today)
- docs/engineering/hub-architecture.md — board/history contract

## Repro Steps
1. Start the hub (`cos hub start`), open the board, click any task whose agent_session id contains a date (e.g. `ses-claude-20260527-...`).
2. The detail drawer shows "loading TASK-NNN.md…" then "loading history…" and stalls for seconds-to-never.
Expected: history loads in well under a second; only real commit SHAs appear.
Actual: `_git_commits_from_worklog` regex matches the 8-digit date `20260527` as a hex SHA and runs `git show` per candidate (5s timeout each, up to 50) on the event loop, freezing the handler; a date that collides with a real short-SHA prefix would also surface a WRONG commit.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a task whose body/frontmatter contains a date-like all-digit token (e.g. 20260527), **When** its history is fetched, **Then** that token is not resolved as a commit and no spurious commit appears in the history.
- **Given** the hub is serving requests, **When** the history/list/detail endpoint does blocking git or sqlite work, **Then** the FastAPI event loop is not blocked (handler runs in the threadpool) and concurrent requests stay responsive.
- **Given** a history fetch the server is slow to answer, **When** it exceeds the client timeout, **Then** the UI shows an error state instead of an infinite "loading history…" spinner.

## Work Log
- 2026-06-08 [claude]: Fixed history hang: _git_commits_from_worklog now batch-validates candidate SHAs via one `git cat-file --batch-check` (d
- 2026-06-08 [claude]: committed 6d52ad39: src/core/board_os/mcp_tools.py, src/core/web/routes/board.py, src/core/web/ui/src/lib/api-client.ts
