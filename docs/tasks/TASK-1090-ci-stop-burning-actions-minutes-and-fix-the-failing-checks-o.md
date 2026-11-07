---
id: TASK-1090
title: "CI: stop burning Actions minutes and fix the failing checks on main"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-11-07
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1090: CI: stop burning Actions minutes and fix the failing checks on main

**Outcome (one sentence):** The Actions quota is no longer drained (root cause named), every test runs once per push instead of three to four times, and main's CI is green again.

## Read First
- docs/engineering/ci-gates.md
- .github/workflows/ci.yml

## Repro Steps
1. GitHub billing mail 2026-11-07: 2,000 / 2,000 included minutes used in 7 days.
2. CI on 003e5d60: 6 failing checks (pytest x3, coverage, slow suite, docs-lint), CI Pass red.
Expected: quota lasts the month; CI Pass green.
Actual: Dana publish-web dispatched every 5 minutes in `check` mode from 10-31 to 11-02 (~495 runs x ~4.3 min); coding-os (public, unbilled) ran each suite 3-4x per push plus a daily full cron; the cognition cut left a migration test and two slow test classes red.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the per-repo run history for November
- **When** the CI workflows are restructured and the failing tests fixed
- **Then** each suite runs once per push on Linux/3.12, the cron is weekly, the failing tests pass locally, docs-lint passes, and the minute root cause is reported with evidence

## Work Log
- 2026-11-07 [claude]: Minutes: coding-os is PUBLIC (unbilled); November billable use is private repos, 1,422 of ~1,900 measured minutes…
