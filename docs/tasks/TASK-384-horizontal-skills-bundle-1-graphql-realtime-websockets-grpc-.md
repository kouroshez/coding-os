---
id: TASK-384
title: "Horizontal skills bundle 1 \u2014 graphql, realtime/websockets, grpc-microservices"
swimlane: core
kind: feature
epic: E-skills
labels: [backlog, onboarding-program, ready]
status: icebox
priority: P2
appetite: 2d
created: 2026-06-11
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-384: Horizontal skills bundle 1 — graphql, realtime/websockets, grpc-microservices

**Outcome (one sentence):** Three new core skills (graphql, realtime-websockets, grpc-microservices) authored to the public skill standard with schema-valid frontmatter and trigger evals.

## Read First
- src/core/schemas/skill.schema.json
- src/core/skills/api-design/SKILL.md (closest sibling — overlap boundary must be explicit)
- docs/engineering/skill-architecture.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** each new SKILL.md, **When** `load_skill_registry(src/core/skills)` runs, **Then** schema-valid frontmatter (tier/domain enums) with zero warnings.
- **Given** the api-design skill, **When** the three skills are reviewed, **Then** each states its non-overlap boundary with api-design in the description (no two skills with overlapping triggers — anti-overengineering rule).
- **Given** trigger evals, **When** the routing fixture runs, **Then** each skill triggers on its intended keywords/globs and NOT on counterexamples.
- **Given** docs, **When** `make docs-lint` runs, **Then** green.

## Work Log
