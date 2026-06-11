---
id: TASK-375
title: "Stack: spring-boot \u2014 full bundle via factory (new java skill)"
swimlane: templates
kind: feature
epic: D-catalog
labels: [backlog, onboarding-program, ready]
status: icebox
priority: P2
appetite: 2d
created: 2026-06-11
started: null
completed: null
agent_session: null
depends_on: [TASK-361]
blocked_by: []
references: []
---

# TASK-375: Stack: spring-boot — full bundle via factory (new java skill)

**Outcome (one sentence):** Complete spring-boot stack bundle including a new java/spring-boot skill (language=java, java-plain stack included) passing the factory lint — first enterprise-JVM coverage.

## Read First
- docs/playbooks/template-authoring.md
- src/templates/go-plain/stack.yaml (plain-language stack pattern, TASK-348)
- docs/engineering/project-anatomy.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the language layer (TASK-348), **When** `java-plain` + `spring-boot` stacks load, **Then** bare-language pick "java" resolves to java-plain and spring-boot declares language=java.
- **Given** the factory contract, **When** `cos init --template spring-boot --yes --no-index --no-register` runs, **Then** scaffold lands under structure.root with a runnable Maven/Gradle skeleton and resolved placeholders.
- **Given** the new java + spring-boot SKILL.md files, **When** the skill registry loads, **Then** schema-valid frontmatter with no warnings.
- **Given** the matrix, **When** `uv run pytest tests/test_template_scaffold.py tests/test_anatomy_contract.py -q` runs, **Then** green including golden fixtures.

## Work Log
