---
id: TASK-1077
title: "Hub SSE: release background-tab stream connections so tabs stop exhausting the 6-socket pool"
swimlane: core
kind: bug
epic: null
labels: [docs-update, hub, ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-10-25
started: 2026-10-24
completed: null
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1077: Hub SSE: release background-tab stream connections so tabs stop exhausting the 6-socket pool

**Outcome (one sentence):** A Hub tab that is not visible holds no SSE connection, so a few open tabs can no longer starve index.html and API fetches of the browser's 6-connection-per-origin HTTP/1.1 pool.

## Read First
- docs/engineering/hub-architecture.md
- src/core/web/ui/src/lib/shared-event-source.ts

## Repro Steps
With two Hub tabs open in Brave (4 SSE sockets held), drive a third via Playwright: overview -> chat navigation times out at 20s; lsof shows Brave holding exactly 6 ESTABLISHED sockets to 127.0.0.1:9188 while the server answers curl in 2ms.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a pooled shared stream, **When** the tab stays hidden for the grace period, **Then** the underlying EventSource is closed and the consumers' listeners are kept.
- **Given** a suspended stream, **When** the tab becomes visible, **Then** a new EventSource opens on the same URL and every kept listener receives its events.
- **Given** the browser gave up (CLOSED), **When** a consumer acquires the URL again, **Then** the same pooled source reconnects instead of being replaced under its existing holders.

## Work Log
