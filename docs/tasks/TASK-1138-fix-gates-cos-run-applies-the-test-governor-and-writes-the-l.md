---
id: TASK-1138
title: "fix(gates): cos run applies the test governor and writes the ledger; blocking hooks fail closed without cos"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: icebox
priority: P1
appetite: 2d
created: 2026-11-26
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1138: fix(gates): cos run applies the test governor and writes the ledger; blocking hooks fail closed without cos

**Outcome (one sentence):** Tests run through cos run are deduped, locked and ledgered by cos run itself, consumer suites match the stack layout, and enforcement does not silently vanish; findings G2, G3 and G4 of docs/engineering/harness-loading-audit-2026-11.md are closed.

## Read First
- docs/engineering/harness-loading-audit-2026-11.md
- docs/engineering/test-governance.md

## Repro Steps
In a fastapi scaffold `cos run test-backend` passes test-governor.sh untouched (fast path needs pytest or make, :28-31) while record-verify-auto ledgers it (audit G2).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a green ledger entry for test-backend on the same tree, **When** `cos run test-backend` runs again, **Then** it is refused unless forced.
- **Given** a scaffold with cos off PATH, **When** a blocking hook fires, **Then** it blocks with an install hint, and an observer hook exits 0.
- **Given** the built wheel, **When** its contents are listed, **Then** core/hooks/_helpers/*.sh is present.

## Work Log
