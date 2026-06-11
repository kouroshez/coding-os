---
id: TASK-352
title: "Skill catalog SSOT \u2014 per-stack tiers + hub preview endpoints"
swimlane: core
kind: feature
epic: E-skills
labels: [wave-1, onboarding-program, ready]
status: testing
priority: P1
appetite: 1d
created: 2026-06-11
started: 2026-06-11
completed: null
agent_session: ses-claude-20260610-185418-2b3f
depends_on: [TASK-348]
blocked_by: []
references: []
---
# TASK-352: Skill catalog SSOT — per-stack tiers + hub preview endpoints

**Outcome (one sentence):** Skill registry (existing skill_registry.py + skill.schema.json) exposes required/recommended/optional tiers per stack; GET /api/hub/skills and GET /api/hub/stacks/{id}/skills serve the onboarding preview; CLI skill listing consumes the same SSOT.

## Read First
- src/cli/skill_registry.py
- src/core/schemas/skill.schema.json
- src/core/web/routes/hub.py
- src/core/web/routes/config.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a stack id, **When** GET /api/hub/stacks/{id}/skills is called, **Then** the response groups skills into required/recommended/optional with name, tier, domain and description sourced from frontmatter (no duplicated data file).
- **Given** the hub-global catalog, **When** GET /api/hub/skills is called, **Then** all core + stack skills are listed with provenance (core vs stack) and schema validation status.
- **Given** the CLI, **When** the skill listing command runs with --stack, **Then** output matches the endpoint payload (same SSOT function) and tests cover both consumers staying in sync.
- **Given** the verification matrix, **When** `uv run pytest tests/test_cli.py -q` plus a web-route test run, **Then** green.

## Work Log
- 2026-06-11 [claude]: IMPL DONE (parked in testing per batch cadence) — collect_stack_skill_groups + collect_skill_catalog in skills_list.py a
