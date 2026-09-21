---
id: TASK-1044
title: "The Hub SPA has no coverage gate while Python enforces 62% + diff-cover 80%"
swimlane: core
kind: test
epic: null
labels: [parked, ready]
status: complete
priority: P3
appetite: 1d
created: 2026-09-18
started: 2026-09-20
completed: 2026-09-20
agent_session: ses-claude-20260920-211122-bc06
depends_on: []
blocked_by: []
references: []
---
# TASK-1044: The Hub SPA has no coverage gate while Python enforces 62% + diff-cover 80%

**Outcome (one sentence):** The Hub SPA carries a coverage floor CI enforces, set from a measured baseline rather than a guessed one — or the asymmetry with the Python side is recorded as deliberate.

## Read First
- docs/engineering/ci-gates.md § The gates
- src/core/web/ui/vitest.config.ts
- .github/workflows/ci.yml (the `coverage` job)

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** `@vitest/coverage-v8` installed
**When** `npm run test:coverage` runs
**Then** it prints a real number for the SPA, and that number — not a guess — becomes the floor.

**Given** the floor is set
**When** a PR drops SPA coverage below it
**Then** CI fails, through `CI Pass` like every other enforced gate.

**Given** the decision goes the other way
**When** the asymmetry is accepted
**Then** ci-gates.md records why the SPA is exempt, so the next reader does not re-file this.

## Work Log
- 2026-09-21 [claude]: Attempted the measurement the card calls for and it is blocked by tooling, not by effort. Adding @vitest/coverage-v8…
- 2026-09-21 [claude]: Measured, then gated. @vitest/coverage-v8@4.1.11 installs fine on a clean tree — the earlier arborist crash was a…
- 2026-09-21 [claude]: commit 26617ee4be — ci(web): gate the Hub SPA on measured vitest coverage thresholds
- 2026-09-21 [claude]: Status transitioned to complete via cos task-done.
