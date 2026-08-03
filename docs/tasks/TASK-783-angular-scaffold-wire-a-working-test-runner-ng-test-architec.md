---
id: TASK-783
title: "angular scaffold: wire a working test runner (ng test architect target + karma/jasmine devDeps + tsconfig.spec) so a sample spec runs green day-one"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-07-04
started: 2026-07-04
completed: 2026-07-04
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-783: angular scaffold: wire a working test runner (ng test architect target + karma/jasmine devDeps + tsconfig.spec) so a sample spec runs green day-one

**Outcome (one sentence):** The angular seed's `npm test` (ng test) actually runs on Angular v22's current-stable runner — `@angular/build:unit-test` on Vitest + jsdom — with a test architect target, tsconfig.spec.json, and a re-added health.service.spec.ts, so day-one verify is green (karma/jasmine is removed in v22; the naive karma spec was reverted precisely because it turned verify RED).

## Read First
- src/templates/angular/scaffold/src/frontend/angular.json (test architect target)
- src/templates/angular/scaffold/src/frontend/package.json

## Repro Steps
1. Render the angular scaffold; `cd src/frontend && npm install && npm test`.
Expected: the test runner runs and the sample spec passes (exit 0).
Actual (before fix): `ng test` had NO configured runner (no test architect target, no runner devDeps, no spec) so verify was RED.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the rendered angular scaffold **When** running `npm test` (`ng test --watch=false`) **Then** the `@angular/build:unit-test` builder (Vitest + jsdom) runs once and health.service.spec.ts passes — exit 0, no Chrome needed.
- **Given** `npm run build` and `npm run lint` **When** run day-one **Then** both pass on Angular v22.

## Work Log
- 2026-07-04 [claude]: Wired a working `ng test` runner. Angular v22's current-stable runner is @angular/build:unit-test on Vitest+jsdom (karma/jasmine removed in v22), so wired that: angular.json test target, tsconfig.spec.json, vitest devDep, and a health.service.spec.ts. Verified: `npx ng test --watch=false` = Test Files 1 passed, Tests 1 passed, run-once exit 0. Committed 0d52c152.
