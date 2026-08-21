---
id: TASK-1013
title: "Replace README hero with brand social card"
swimlane: docs
kind: chore
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-21
started: 2026-08-20
completed: 2026-08-20
agent_session: ses-claude-20260820-192311-0ff4
depends_on: []
blocked_by: []
references: []
---
# TASK-1013: Replace README hero with brand social card

## Outcome

The README opens with a 1280x640 brand card (logo, wordmark, tagline, four capability chips, licence/Scorecard/install line) over the knowledge-graph canvas. The same file is the repository's GitHub social preview, so a link pasted into Slack renders the product instead of GitHub's auto-generated card — which prints the star count.

## Read First

- `README.md` line 19 — the hero image reference
- `docs/assets/hero-card.webp` — the new asset (64 KB)
- `docs/assets/hub/graph-explorer.webp` — source screenshot for the right half

## Acceptance

- GIVEN the README renders, WHEN a reader lands on it, THEN the brand card is the first image and the three-layer diagram follows directly beneath it.
- GIVEN the asset is committed, WHEN `make docs-lint` runs, THEN it reports 0 errors.
- GIVEN GitHub's 1 MB social-preview ceiling, WHEN the asset is measured, THEN it is well under it (64 KB) at exactly 1280x640.

## Work Log
- 2026-08-21 [claude]: Edit README.md
- 2026-08-21 [claude]: commit 627c25136a — docs(readme): lead with a brand card showing the knowledge graph
- 2026-08-21 [claude]: Composed the card in HTML over the graph-explorer canvas and rendered it with headless Chrome at 1280x640; four…
- 2026-08-21 [claude]: Status transitioned to complete via cos task-done.
