---
id: TASK-965
title: "Clear GHSA-qv9r-c865-cp47: spring-boot scaffold inherits log4j-api 2.24.3"
swimlane: templates
kind: bug
epic: null
labels: [supply-chain, scaffold, ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-08-13
started: 2026-08-13
completed: null
agent_session: ses-claude-20260812-170221-1654
depends_on: []
blocked_by: []
references: []
---
# TASK-965: Clear GHSA-qv9r-c865-cp47: spring-boot scaffold inherits log4j-api 2.24.3

**Outcome (one sentence):** The spring-boot scaffold no longer ships a log4j-api affected by CVE-2026-49844, so Scorecard Vulnerabilities returns to 10 and consumers of `cos init --stack spring-boot` do not inherit the advisory.

## Read First
- src/templates/spring-boot/scaffold/src/backend/pom.xml
- docs/engineering/ci-gates.md

## Repro Steps
gh api repos/:owner/:repo/code-scanning/alerts?state=open reports VulnerabilitiesID #131 -> GHSA-qv9r-c865-cp47. spring-boot-starter-parent 3.5.16 manages log4j2.version 2.24.3; the advisory is fixed in 2.25.5. src/templates/spring-boot/scaffold/src/backend/pom.xml does not override it.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the spring-boot scaffold pom, **When** its effective log4j-api version is resolved, **Then** it is >= 2.25.5. **Given** osv-scanner over the templates, **When** run, **Then** GHSA-qv9r-c865-cp47 no longer matches.

## Work Log
- 2026-08-13 [claude]: Edit pom.xml
