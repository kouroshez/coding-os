---
id: TASK-1110
title: "fix(hooks): the banner drops the supervision route when supervision is off or its policy changes"
swimlane: "board_os"
kind: bug
epic: null
labels: [hooks, supervision, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-11-24
started: 2026-11-24
completed: 2026-11-24
agent_session: ses-claude-20261124-100023-d989
depends_on: []
blocked_by: []
references: []
---
# TASK-1110: fix(hooks): the banner drops the supervision route when supervision is off or its policy changes

**Outcome (one sentence):** The banner's sup= field always reflects the current Hub policy: absent when supervision is off, re-resolved when the routing policy changes mid-session.

## Read First
- src/core/hooks/resolve-supervise-route.sh
- src/core/rules/transparency-banner.md

## Repro Steps
Supervision was turned off in the Hub at 23:20, yet every banner since still shows sup=claude/claude-fable-5-1: resolve-supervise-route.sh exits on enabled=false without removing the panel's .supervise-route, and its debounce signature is only the gate class, so a policy edit is never re-resolved either.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a panel with a resolved route, **When** supervision is turned off and the next prompt arrives, **Then** .supervise-route and its debounce marker are removed and the banner has no sup= field.
- **Given** supervision is on, **When** the routing policy changes in hub-settings.json, **Then** the next prompt re-resolves the route even if the gate class is unchanged.

## Work Log
- 2026-11-24 [claude]: commit 1a19e14b0b — fix(hooks): the banner drops the supervision route when supervision is off or its policy changes
- 2026-11-24 [claude]: commit c84fb4e8e8 — fix(hooks): sort the routing policy before hashing it, and test the rendered banner
- 2026-11-24 [claude]: Status transitioned to complete via cos task-done.
