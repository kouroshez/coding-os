---
id: TASK-291
title: "Hub SPA shows a blank white screen on first paint until the 1MB bundle mounts"
swimlane: core
kind: bug
epic: hub-redesign
labels: [hub, ui, perf, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-09
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260609-151118-a8c3
depends_on: []
blocked_by: []
references: []
---
# TASK-291: Hub SPA shows a blank white screen on first paint until the 1MB bundle mounts

**Outcome (one sentence):** First page load (and hard-refresh) shows an instant branded loading placeholder instead of a blank unstyled screen while the JS bundle downloads and React mounts.

## Read First
- src/core/web/ui/index.html
- src/core/web/ui/src/main.tsx
- docs/engineering/hub-architecture.md

## Repro Steps
1. Hard-refresh the Hub (`http://127.0.0.1:9188`) or open it on a cold cache.
2. Observe a blank, unstyled white/dark screen for the time it takes the ~1MB single JS bundle to download + parse and React to mount.
3. The chat/board UI only appears after mount; before that there is no loading affordance.
Expected: an instant branded loading placeholder until the app mounts.
Actual: blank screen — reads as "styles/components didn't load".

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a cold-cache load or hard-refresh of the Hub, **When** the browser has parsed `index.html` but not yet mounted React, **Then** an inline loading placeholder (logo/spinner on the themed background) is visible instead of a blank screen.
- **Given** React mounts, **When** `createRoot().render()` runs, **Then** the placeholder is replaced by the app with no leftover/flash.
- **Given** light or dark theme, **When** the placeholder shows, **Then** its background matches the themed canvas (no white flash in dark mode).

## Work Log
- 2026-06-09 [claude]: Root cause: empty #root + un-split ~1MB JS bundle = blank unstyled first paint until React mounts (worse right after a h
