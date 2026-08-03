---
id: TASK-785
title: "Fix Hub board AGENT STREAM/Tweaks side-panels overlapping the toolbar buttons and zoom controls"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-07-04
started: 2026-07-04
completed: 2026-07-04
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-785: Fix Hub board AGENT STREAM/Tweaks side-panels overlapping the toolbar buttons and zoom controls

**Outcome (one sentence):** The right-docked LiveStreamPanel (AGENT STREAM) and TweaksPanel no longer cover the board's top toolbar buttons (stream/flat/archive/tweaks) or the bottom-right zoom controls — they sit between the toolbar and the zoom bar.

## Read First
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx

## Repro Steps
Open the Hub board, toggle AGENT STREAM on (default): the fixed panel (top:110, bottom:14, zIndex:50) overlays the toolbar's right buttons and the bottom zoom bar (zIndex:45), hiding them. TweaksPanel shares the same top:110/bottom:14 pattern.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the board with AGENT STREAM open **When** the panel renders **Then** the toolbar's right-side buttons and the bottom zoom controls stay fully visible and clickable. **Given** the Tweaks panel open **When** it renders **Then** the same chrome stays visible. **Given** the board content **When** the panel is open **Then** columns still clear the panel (paddingRight unchanged).

## Work Log
- 2026-07-04 [claude]: Edit CosBoardPage.tsx
- 2026-07-04 [claude]: Edit CosBoardPage.tsx
- 2026-07-04 [claude]: Constrained the three right-docked board side-panels so they no longer cover the toolbar buttons or the bottom zoom…
- 2026-07-04 [claude]: committed ca567ef1 · 1 file
- 2026-07-04 [claude]: Status transitioned to complete via cos task-done.
