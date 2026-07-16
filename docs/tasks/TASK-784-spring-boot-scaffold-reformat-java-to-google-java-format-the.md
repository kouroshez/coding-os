---
id: TASK-784
title: "spring-boot scaffold: reformat Java to google-java-format then re-bind spotless:check to the verify phase"
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
agent_session: ses-claude-20260703-211955-5bf7
depends_on: []
blocked_by: []
references: []
---
# TASK-784: spring-boot scaffold: reformat Java to google-java-format then re-bind spotless:check to the verify phase

**Outcome (one sentence):** The spring-boot scaffold Java is google-java-format compliant (2-space indent, collapsed empty record bodies) so `./mvnw spotless:check` passes, and spotless:check is bound to the verify phase so `./mvnw verify` honestly lints.

## Read First
- src/templates/spring-boot/scaffold/src/backend/pom.xml
- docs/playbooks/template-authoring.md (Stack bundle standard — verify/lint row)

## Repro Steps
1. Render the spring-boot scaffold; `cd src/backend && ./mvnw -q -DskipTests spotless:check` (the `lint-backend` target).
Expected: BUILD SUCCESS.
Actual (before fix): BUILD FAILURE — scaffold Java is 4-space, google-java-format requires 2-space, and no execution bound spotless:check to a phase so `./mvnw verify` skipped it silently.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the rendered spring-boot scaffold **When** running `./mvnw verify` (which now includes the bound `spotless:check`) and `lint-backend` (`spotless:check`) **Then** both pass day-one (BUILD SUCCESS) because the Java is google-java-format compliant.
- **Given** a mis-formatted Java file **When** `./mvnw verify` runs **Then** it fails with "format violations" — proving the check is enforced, not a no-op.

## Work Log
- 2026-07-04 [claude]: Reformatted scaffold Java to google-java-format (gjf 1.35.0, 2-space + collapsed record body); bumped spotless-maven-plugin to 2.44.5 with pinned gjf 1.35.0 and bound spotless:check to the verify phase. Verified end-to-end: rendered scaffold + `./mvnw verify` = BUILD SUCCESS (test green, spotless-check runs in verify); negative test (mis-indented file) turns verify RED with format violations. Committed 9cfdfb88.
