---
id: TASK-1085
title: "Hub QA pass: responsive widths, light/dark themes, UI/UX polish"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-10-25
started: 2026-10-25
completed: 2026-10-25
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1085: Hub QA pass: responsive widths, light/dark themes, UI/UX polish

**Outcome (one sentence):** Every Hub screen renders without horizontal overflow at phone, tablet and desktop widths and stays legible in both light and dark themes.

## Read First
- docs/engineering/hub-architecture.md

## Repro Steps
1. Open each Hub route at 375px, 768px and 1280px widths, in light and in dark theme.
2. Measure `document.documentElement.scrollWidth > clientWidth` and low-contrast text.
Expected: no page-level horizontal scroll, readable text in both themes, no console errors.
Actual: to be measured in this pass.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the Hub at 375px, 768px and 1280px in light and dark theme
- **When** every top-level route is opened
- **Then** no page scrolls horizontally, no console error or 4xx/5xx API response appears, and each defect found is fixed or recorded with its reason

## Work Log
- 2026-10-25 [claude]: Status transitioned to complete via cos task-done.
- 2026-10-25 [claude]: Swept 18 routes x 375/768/1280 x light/dark: the header overflowed every route below 1280px; fixed with a wrapping…
