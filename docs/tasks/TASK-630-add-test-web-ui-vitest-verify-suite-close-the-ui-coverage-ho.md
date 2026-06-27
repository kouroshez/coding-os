---
id: TASK-630
title: "Add test-web-ui (vitest) verify-suite \u2014 close the UI coverage hole (record-filter+golden)"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: icebox
priority: P3
appetite: 1d
created: 2026-06-27
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-630: Add test-web-ui (vitest) verify-suite — close the UI coverage hole (record-filter+golden)

**Outcome (one sentence):** An edit under src/core/web/ui/** maps to a verify-suite (vitest) so the agent is gated/told to run UI tests at task-done, closing the F-TST-1 coverage hole where UI edits record no matrix verify. Done WITHOUT creating an unsatisfiable gate.

## Read First
- src/core/board_os/verify-suites.yaml
- src/core/hooks/record-verify-auto.sh
- Makefile

## Repro Steps
verify-suites.yaml has NO entry for src/core/web/ui/** (vitest exists: package.json test=vitest run); record-verify-auto.sh:20-32 hardcodes the recordable suite verbs (pytest|make verify-hooks|make docs-lint), so a raw npm/vitest suite would never record → unsatisfiable gate.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a src/core/web/ui/** change **When** the agent closes the task **Then** verify-suites maps it to test-web-ui and the gate is satisfiable. - **Given** the agent runs the suite command **When** it exits 0 **Then** record-verify-auto.sh records the PASS (so the gate is satisfiable, not a deadlock). - **Given** vitest is run via the suite command **Then** it is `make ui-test`, not a raw npm (record-verify-auto only matches make/pytest verbs).

## Work Log
