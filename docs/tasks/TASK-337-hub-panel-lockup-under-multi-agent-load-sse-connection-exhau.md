---
id: TASK-337
title: "Hub: panel lockup under multi-agent load \u2014 SSE connection exhaustion + event-loop blocking"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-10
started: 2026-06-10
completed: 2026-06-10
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-337: Hub: panel lockup under multi-agent load — SSE connection exhaustion + event-loop blocking

**Outcome (one sentence):** Hub stays responsive with multiple agents working and multiple tabs open: one shared EventSource per stream path per tab (board tab drops 4 SSE conns to 2, under the browser's 6-per-origin HTTP/1.1 cap), and no sync SQLite/file/git work runs on the uvicorn event loop (sync handlers run on the threadpool; SSE tick work offloaded via asyncio.to_thread).

## Read First
- docs/engineering/hub-architecture.md
- src/core/web/routes/stream.py
- src/core/web/routes/board.py
- src/core/web/ui/src/lib/use-event-stream.ts
- src/core/web/ui/src/features/cos-board/useBoardStream.ts

## Repro Steps
1. Open the hub board view in 2+ browser tabs (each tab holds 4 SSE connections: useBoardStream + AttentionBell + LiveAgentsPanel on /api/stream/events, LiveStatus on /api/hooks/stream) while 2+ agent sessions are actively writing to coding-os.db.
2. Start a chat stream or navigate between pages in one tab.
Expected: every tab loads and stays interactive.
Actual: tabs hang on load / panel freezes — browser's 6-per-origin HTTP/1.1 connection cap is exhausted by SSE, and on the server sync SQLite/file/git work inside `async def` handlers + SSE pollers blocks the single uvicorn event loop (up to 5s per locked-DB wait, 8s per git subprocess).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** one tab on the board view, **When** it is open, **Then** it holds at most 2 SSE connections (one shared /api/stream/events, one shared /api/hooks/stream) — shared-EventSource consumers covered by unit test.
- **Given** agents holding the SQLite write lock or a slow git subprocess, **When** the panel calls board/graph/search/logs routes, **Then** the event loop is never blocked: sync-work handlers are plain `def` (threadpool) and SSE generator ticks run via `asyncio.to_thread`.
- **Given** the existing web + UI test suites, **When** run, **Then** they pass.

## Work Log
- 2026-06-10 [claude]: Status transitioned to complete via cos task-done.
- 2026-06-10 [claude]: commit 35304d9b56 — fix(hub): panel lockup under multi-agent load — shared SSE pool + threadpool routes
