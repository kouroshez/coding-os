---
id: TASK-172
title: "Centered task-detail modal replacing the right-edge drawer"
swimlane: core
kind: feature
epic: agent-hub
labels: [ready]
status: complete
priority: P2
appetite: "4h"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260605-183120-db30
depends_on: []
blocked_by: []
references: []
---
# TASK-172: Centered task-detail modal replacing the right-edge drawer

**Outcome (one sentence):** Clicking a board card opens a CENTERED modal (dim backdrop, ~960px max-width, ~90vh max-height, rounded, fade/scale-in) instead of a right-edge drawer, closable via Esc and overlay click, with all existing sub-panels (markdown body, history, transcript, inline edit) intact.

## Read First
- docs/engineering/agent-hub-orchestration.md
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a user clicks a board card
- **When** the task detail opens
- **Then** it renders as a centered modal over a dim backdrop (not glued to the right edge), closes on Esc and overlay click, and preserves every sub-panel (body / history / transcript / inline edit) with internal scroll; the build (`make ui-build`) succeeds.

## Work Log
- 2026-06-05 [claude]: TaskDetailDrawer panel re-geometried from right-edge slide-in to a centered modal (translate -50/-50, maxHeight 90vh, ro
