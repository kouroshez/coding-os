---
id: TASK-659
title: "Apply ultra-code-review findings: preserve exec bit in renderer, node-express Node21 glob, astro doc drift"
swimlane: cli
kind: bug
epic: stack-completeness-v2
labels: [review, renderer, wave-2, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-30
started: 2026-06-30
completed: 2026-06-30
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-659: Apply ultra-code-review findings: preserve exec bit in renderer, node-express Node21 glob, astro doc drift

**Outcome (one sentence):** The renderer preserves the source file mode (mvnw stays 0755 so spring-boot/java-plain `./mvnw` works day-one), the node-express test script + scaffold-verify CI run on a Node that supports the test-runner glob, and astro-app.md no longer documents the removed RFC 9457 shape.

## Read First
- src/cli/main.py
- src/templates/node-express/scaffold/src/backend/package.json
- src/templates/astro/scaffold/docs/playbooks/astro-app.md

## Repro Steps
Ultra-code-review of the session diff CONFIRMED: (1) src/cli/main.py:887 _overlay_scaffold now read_text+write_text's text files at 0644, dropping the 100755 bit on spring-boot/java-plain mvnw -> `./mvnw` fails 'permission denied' on cos init; (2) node-express package.json test `node --import tsx --test \"src/**/*.test.ts\"` needs Node>=21 glob support, but scaffold-verify.yml pins node-version 20 -> Test gate red; (3) astro-app.md still references RFC 9457 application/problem+json after problem.ts migrated to the canonical envelope.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** cos init --template spring-boot, **When** rendered, **Then** src/backend/mvnw is mode 0755 (executable). **Given** scaffold-verify CI, **When** the node-express job runs, **Then** `npm test` finds + passes the sample test. **Given** astro-app.md, **When** read, **Then** it describes the canonical {error:{code,message,request_id}} envelope, not RFC 9457.

## Work Log
- 2026-06-30 [claude]: Edit main.py
- 2026-06-30 [claude]: Edit scaffold-verify.yml
- 2026-06-30 [claude]: Edit astro-app.md
- 2026-06-30 [claude]: Edit package.json
- 2026-06-30 [claude]: committed 81d5434b · 5 files
- 2026-06-30 [claude]: Fixed renderer exec-bit (copymode, verified mvnw 0755), node-express Node>=21 (CI node22+engines), astro doc.…
