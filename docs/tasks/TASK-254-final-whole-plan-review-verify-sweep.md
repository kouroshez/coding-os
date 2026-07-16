---
id: TASK-254
title: "Final whole-plan review + verify sweep"
swimlane: core
kind: chore
epic: hub-redesign
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-20260608-024900-f2b0
depends_on: []
blocked_by: []
references: []
---
# TASK-254: Final whole-plan review + verify sweep

**Outcome (one sentence):** Review the whole Hub redesign for enterprise quality, coverage and no regressions; run the full verify sweep.

## Read First
- docs/engineering/hub-architecture.md — the Hub contract to check against.
- AGENTS.md (Verification Matrix) — the full-sweep commands.
- git log (the shipped feat(hub)/fix(hub) commits) — what to re-verify.

## Context / Approach
After the redesign tasks land: run full pytest + UI vitest, re-walk each original user ask, check anti-overengineering + a11y + dogfood (validate in a scaffolded `cos init` consumer, not just the meta-repo), and confirm no regressions. Final close of the hub-redesign epic. Depends on the other 12 tasks.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the redesign complete, **When** running full pytest + UI vitest, **Then** all green.
- **Given** each plan ask, **When** reviewed, **Then** it is verified delivered or explicitly deferred with a reason.

## Work Log
- 2026-06-08 [claude]: Whole-plan review: 11 hub-redesign/kernel tasks shipped + committed. Verified: UI full vitest 102/102, thinking_os 1480,
