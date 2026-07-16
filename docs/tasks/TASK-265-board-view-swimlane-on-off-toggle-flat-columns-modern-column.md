---
id: TASK-265
title: "Board view: swimlane on/off toggle (flat columns) + modern column headers + WIP tooltip"
swimlane: core
kind: feature
epic: hub-redesign
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-618-2ab7
depends_on: []
blocked_by: []
references: []
---
# TASK-265: Board view: swimlane on/off toggle (flat columns) + modern column headers + WIP tooltip

**Outcome (one sentence):** A Tweaks toggle collapses the swimlane grid into flat status columns so every active task is visible without scrolling lanes; column headers gain a per-status accent bar and a WIP tooltip that explains the limit.

## Read First
- src/core/web/ui/src/features/cos-board/types.ts — BoardTweaks/DEFAULT_TWEAKS
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx — COLUMN_META, column header (~684), swimlanes render (~777), TweaksPanel (~1820)
- src/core/web/ui/src/features/cos-board/BoardThemeProvider.tsx — tweaks init (no localStorage persistence)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the Tweaks panel, **When** "Swimlane grid" is toggled off, **Then** the board renders flat status columns containing every filtered task regardless of swimlane, each card keeping its swimlane colour, and drag-to-column still changes status without changing the task's lane.
- **Given** the default board load, **When** no tweak has been changed, **Then** the swimlane grid renders exactly as before (showSwimlanes defaults true; not persisted so a reload never silently flips to flat).
- **Given** a column header, **When** it has a WIP cap, **Then** it shows "N / cap WIP" with a hover tooltip explaining WIP, and a per-status accent bar tops every column header.

## Work Log
- 2026-06-08 [claude]: Added showSwimlanes to BoardTweaks (default true, not persisted); gated the swimlane grid with `&&` and appended a flat-
