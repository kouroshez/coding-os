---
id: TASK-1054
title: "Hub decides SPA availability per request so a missing or rebuilt dist never 404s deep links"
swimlane: core
kind: bug
epic: null
labels: [hub, web, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-10-07
started: 2026-10-07
completed: 2026-10-07
agent_session: ses-claude-20261004-231430-d18a
depends_on: []
blocked_by: []
references: []
---
# TASK-1054: Hub decides SPA availability per request so a missing or rebuilt dist never 404s deep links

**Outcome (one sentence):** The Hub checks for src/core/web/ui/dist on every request: a `make ui-build` is served on the next request without a hub restart, and while dist is missing every SPA route answers with the build instructions (503) instead of a bare JSON 404.

## Read First
- src/core/web/server.py
- docs/engineering/hub-architecture.md

## Repro Steps
2026-10-07: dist/ and node_modules/ were removed at 15:14 while the hub ran. /p/coding-os/board returned {"detail":"Not Found"}. After `make ui-build` (which prints "hub picks up automatically") the same URL still 404s, because server.py picks the SPA-or-placeholder routes once in create_app().

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** dist is missing, **When** GET /p/coding-os/board, **Then** 503 HTML naming `make ui-build`, and /api/* unknown paths still 404 JSON.
- **Given** the hub started without dist, **When** `make ui-build` runs, **Then** the next GET /p/coding-os/board is 200 index.html with no restart.
- **Given** dist exists, **When** a hashed /assets file or root file is requested, **Then** it is served as before, and path traversal still 404s.

## Work Log
- 2026-10-07 [claude]: Edit hub-architecture.md
- 2026-10-07 [claude]: Edit server.py
- 2026-10-07 [claude]: Edit server.py
- 2026-10-07 [claude]: Edit server.py
- 2026-10-07 [claude]: Edit test_hub_spa_serving.py
- 2026-10-07 [claude]: Fixed: one per-request catch-all replaces the startup-time SPA/placeholder split and the /assets StaticFiles mount…
- 2026-10-07 [claude]: commit a0c4407734 — fix(web): serve the hub SPA per request so a missing or rebuilt dist never 404s deep links
- 2026-10-07 [claude]: Status transitioned to complete via cos task-done.
