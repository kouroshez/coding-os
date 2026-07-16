---
id: TASK-776
title: "Fix stack verify/lint correctness + day-one sample tests (spring-boot, nextjs, angular, laravel, wordpress)"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-07-04
started: 2026-07-04
completed: 2026-07-04
agent_session: ses-claude-20260703-210450-473d
depends_on: []
blocked_by: []
references: []
---
# TASK-776: Fix stack verify/lint correctness + day-one sample tests (spring-boot, nextjs, angular, laravel, wordpress)

**Outcome (one sentence):** Five stacks whose `verify:` block claims a lint/test suite it does not actually run are made honest and day-one green — spring-boot binds spotless to the `verify` phase, nextjs runs its vitest sample, and angular/laravel/wordpress each ship one runnable sample test so `cos stack-lint` stops reporting the soft "no sample test" GAP.

## Read First
- docs/playbooks/template-authoring.md § Stack bundle standard (rows 2, 15)
- src/templates/spring-boot/scaffold/src/backend/pom.xml
- src/templates/nextjs/stack.yaml

## Acceptance
- **Given** a fresh `cos init` of each stack, **When** the stack's `verify:` cmd runs, **Then** it actually executes the lint AND test suites its `suites:` label names (no silent skip).
- **Given** `cos stack-lint`, **When** it audits angular/laravel/wordpress/nextjs, **Then** none reports "no sample test" and none reports a verify/suite mismatch.
- **Given** spring-boot, **When** `cd src/backend && ./mvnw -q verify` runs, **Then** spotless:check executes (bound to the verify phase).

## Repro Steps
1. `grep verify src/templates/spring-boot/stack.yaml` → cmd is `./mvnw -q verify` but pom.xml spotless plugin has no `<executions>` → spotless never runs.
2. `grep makefile_targets src/templates/nextjs/stack.yaml` → only `lint-frontend`; verify runs `npm run lint` only, never the shipped `lib/greeting.test.ts`.
3. `cos stack-lint angular` / `laravel` / `wordpress` → each reports soft GAP "no sample test under scaffold/".

## Work Log
- 2026-07-04 [claude]: Edit pom.xml
- 2026-07-04 [claude]: Edit stack.yaml
- 2026-07-04 [claude]: Edit health.service.spec.ts
- 2026-07-04 [claude]: Edit HealthStatus.php
- 2026-07-04 [claude]: Edit phpunit.xml
- 2026-07-04 [claude]: Edit HealthStatusTest.php
- 2026-07-04 [claude]: Edit health.php
- 2026-07-04 [claude]: Edit phpunit.xml
- 2026-07-04 [claude]: Edit HealthStatusTest.php
- 2026-07-04 [claude]: Edit composer.json
- 2026-07-04 [claude]: Edit HealthController.php
- 2026-07-04 [claude]: Edit composer.json
- 2026-07-04 [claude]: Edit plugin.php
- 2026-07-04 [claude]: Edit stack.yaml
- 2026-07-04 [claude]: Status transitioned to complete via cos task-done.
