---
id: TASK-1017
title: "Regenerate the brand card on a generated backdrop inside the 40pt safe zone"
swimlane: docs
kind: chore
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-21
started: 2026-08-21
completed: 2026-08-21
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-1017: Regenerate the brand card on a generated backdrop inside the 40pt safe zone

## Outcome

The brand card sits on a generated abstract constellation backdrop instead of a cropped Hub screenshot, and every text element clears GitHub's recommended 40pt (80px) safe border. The screenshot version cut node labels mid-word at the right edge and carried leftover UI chrome; the generated backdrop dissolves to black on all four sides, so nothing is lost when a client crops the card.

## Read First

- `docs/assets/hero-card.webp` — the asset the README points at
- `.playwright-mcp/card-gen.html` — the composition source (generated backdrop + HTML typography)

## Acceptance

- GIVEN GitHub's 40pt guidance, WHEN the card is rendered with an 80px guide overlay, THEN no logo, wordmark, tagline, chip, or metadata line crosses it.
- GIVEN the card is exported, WHEN measured, THEN it is 1280x640 and under GitHub's 1 MB social-preview ceiling.
- GIVEN `make docs-lint` runs, THEN it reports 0 errors.

## Work Log
- 2026-08-21 [claude]: Status transitioned to complete via cos task-done.
