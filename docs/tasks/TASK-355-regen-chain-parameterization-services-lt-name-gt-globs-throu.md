---
id: TASK-355
title: "Regen-chain parameterization \u2014 services/&lt;name&gt; globs through skill-enforcement/dimension-registry/boundary"
swimlane: infra
kind: refactor
epic: J-anatomy
labels: [wave-1, onboarding-program, ready]
status: complete
priority: P0
appetite: 2d
created: 2026-06-11
started: 2026-06-10
completed: 2026-06-11
agent_session: ses-claude-20260610-185418-2b3f
depends_on: [TASK-351]
blocked_by: []
references: []
---
# TASK-355: Regen-chain parameterization — services/&lt;name&gt; globs through skill-enforcement/dimension-registry/boundary

**Outcome (one sentence):** Stack glob sources support service-scoped parameterization (src/services/&lt;name&gt;/**) and propagate through `make regen-rules` (skill-enforcement.md, dimension-registry.md), enforce-skill.sh, enforce-scaffold-boundary.sh, adapter template regen and golden tests — no hand-edited derived artifact.

## Read First
- Makefile
- src/core/rules/skill-enforcement.md
- src/core/hooks/enforce-skill.sh
- src/core/hooks/enforce-scaffold-boundary.sh
- src/templates/fastapi/stack.yaml
- docs/governance/critical-rules.md

## Repro / Current Gap
Globs in stack.yaml are static strings (src/backend/**), so a service-scoped install (src/services/ai/) gets zero skill-enforcement and boundary coverage today.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a stack installed under src/services/ai/, **When** regen runs, **Then** skill-enforcement.md and dimension-registry.md contain ai-scoped globs and enforce-skill.sh blocks an uncovered edit beneath that subtree.
- **Given** a classic single-backend project, **When** regen runs, **Then** emitted globs are unchanged vs today (golden diff empty) — full backward compatibility.
- **Given** enforce-scaffold-boundary.sh, **When** a write crosses another service's subtree, **Then** it is flagged using the parameterized boundary data.
- **Given** the matrix, **When** `make verify-hooks` + `uv run pytest tests/test_template_scaffold.py -q` + golden tests run, **Then** all green.

## Work Log
- 2026-06-11 [claude]: committed 8138ccc1: docs/engineering/project-anatomy.md, src/cli/aggregator.py, src/cli/main.py, src/cli/stack_registry.
- 2026-06-11 [claude]: DONE — relocate_profile SSOT in stack_registry (path remap + boundary-aware text swap + -<id> target rename), applied pr
