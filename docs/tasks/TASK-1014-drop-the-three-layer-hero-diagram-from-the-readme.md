---
id: TASK-1014
title: "Drop the three-layer hero diagram from the README"
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
# TASK-1014: Drop the three-layer hero diagram from the README

## Outcome

The README carries one hero image, the brand card. The three-concentric-layers diagram is gone from both the README and the repo — it duplicated an architecture story the prose already tells, and a second hero directly beneath the first split the reader's attention at the exact moment the page has to land.

## Read First

- `README.md` line 19 — the single remaining hero reference
- `docs/assets/hero-card.webp` — the card that stays

## Acceptance

- GIVEN the README renders, WHEN a reader lands on it, THEN exactly one image appears above the sponsor table.
- GIVEN `hero.webp` is deleted, WHEN `make docs-lint` runs with its hard-gated link audit, THEN it reports 0 errors and no dangling image link.
- GIVEN a grep for `hero.webp` across tracked markdown, WHEN it runs, THEN it returns no hits outside `docs/tasks/`.

## Work Log
- 2026-08-21 [claude]: Status transitioned to complete via cos task-done.
- 2026-08-21 [claude]: commit 22d83e0d9c — chore(memory): refresh auto-generated trusted-lessons counters
- 2026-08-21 [claude]: Edit browser-file-upload-blocked-via-cdp.md
- 2026-08-21 [claude]: Edit headless-chrome-beats-the-playwright-extension.md
- 2026-08-21 [claude]: Edit verify-generated-images-by-reading-them-back.md
- 2026-08-21 [claude]: commit 0fb121f4a4 — docs(readme): rebuild the brand card inside GitHub's 40pt safe zone
