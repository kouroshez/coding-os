---
id: TASK-385
title: "Horizontal skills bundle 2 \u2014 messaging/queues, terraform-k8s, search-infra, payments, i18n"
swimlane: core
kind: feature
epic: E-skills
labels: [backlog, onboarding-program, ready]
status: icebox
priority: P3
appetite: 3d
created: 2026-06-11
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-385: Horizontal skills bundle 2 — messaging/queues, terraform-k8s, search-infra, payments, i18n

**Outcome (one sentence):** Five new core skills (messaging-queues, terraform-k8s, search-infra, payments-billing, i18n) authored to the public skill standard with schema-valid frontmatter and trigger evals.

## Read First
- src/core/schemas/skill.schema.json
- src/core/skills/deployment-cicd/SKILL.md (overlap boundary for terraform-k8s)
- docs/engineering/skill-architecture.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** each new SKILL.md, **When** `load_skill_registry(src/core/skills)` runs, **Then** schema-valid frontmatter (tier/domain enums) with zero warnings.
- **Given** sibling skills (deployment-cicd, db-design, a11y), **When** the five are reviewed, **Then** each states its non-overlap boundary in the description; terraform-k8s does not duplicate deployment-cicd content.
- **Given** trigger evals, **When** the routing fixture runs, **Then** each skill triggers on its intended keywords/globs and NOT on counterexamples.
- **Given** docs, **When** `make docs-lint` runs, **Then** green.

## Work Log
