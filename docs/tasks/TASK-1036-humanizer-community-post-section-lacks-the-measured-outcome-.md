---
id: TASK-1036
title: "humanizer community-post section lacks the measured outcome data from the September thread"
swimlane: docs
kind: docs
epic: null
labels: [ready, docs-update]
status: complete
priority: P2
appetite: 1d
created: 2026-09-14
started: 2026-09-20
completed: 2026-09-20
agent_session: ses-claude-20260920-211122-bc06
depends_on: []
blocked_by: []
references: []
---
# TASK-1036: humanizer community-post section lacks the measured outcome data from the September thread

**Outcome (one sentence):** The humanizer skill's community-post section cites what the September threads produced, measured the way this repo can actually measure it, so the lesson rests on two data points rather than one August sample.

## Read First
- src/core/skills/humanizer/SKILL.md § Community posts
- docs/tasks/TASK-1037, TASK-1038, TASK-1039 (the cards the September threads produced)
- git log 60d13900 (the commit that filed them)

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** Reddit scores for the September threads are unobtainable (the API 403s this network and no OAuth credentials exist)
**When** the section is updated
**Then** it cites the outcome git can prove — which threads, which subreddits, which cards, which shipped — and says plainly that no score was read.

**Given** a reader compares the August and September entries
**When** they look for the lesson
**Then** the difference in what each set of posts produced is stated without inventing a causal claim the evidence does not support.

## Work Log
- 2026-09-21 [claude]: Reddit is unreachable, so the card's premise had to change rather than wait: get_me fails outright and…
- 2026-09-21 [claude]: commit b66c742582 — docs(skills): add the September sample to the humanizer community-post section
- 2026-09-21 [claude]: Status transitioned to complete via cos task-done.
