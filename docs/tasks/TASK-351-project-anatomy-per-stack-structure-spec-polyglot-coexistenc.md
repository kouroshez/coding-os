---
id: TASK-351
title: "Project anatomy \u2014 per-stack structure spec + polyglot coexistence contract"
swimlane: core
kind: feature
epic: J-anatomy
labels: [wave-1, onboarding-program, ready]
status: complete
priority: P0
appetite: 2d
created: 2026-06-11
started: 2026-06-10
completed: 2026-06-10
agent_session: ses-claude-20260610-185418-2b3f
depends_on: [TASK-348]
blocked_by: []
references: []
---
# TASK-351: Project anatomy — per-stack structure spec + polyglot coexistence contract

**Outcome (one sentence):** Every stack.yaml declares a canonical `structure:` tree (Go internal/-centric hexagonal, FastAPI routers/schemas/services, Next.js app/, RN screens/); a top-level anatomy contract defines src/{backend|services/&lt;name&gt;|frontend|mobile|shared(+contracts)} so multi-backend stacks coexist; django/fastapi and go/go-fiber glob collisions resolved.

## Read First
- src/core/hooks/enforce-scaffold-boundary.sh
- src/core/schemas/stack.schema.json
- src/templates/_base/scaffold/docs/governance/scaffold-boundary-contract.md
- src/core/rules/skill-enforcement.md
- src/templates/go-fiber/stack.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the schema extension, **When** all 8+ stack.yaml files are validated, **Then** each declares `structure:` with its canonical tree and the engineering doc (docs/engineering/project-anatomy.md) records the top-level contract incl. shared/contracts as the only cross-language boundary.
- **Given** a project composing two backends (go-fiber + fastapi), **When** scaffolded, **Then** each lands under src/services/&lt;name&gt;/ with no path or glob collision, and single-backend projects keep the simple src/backend layout unchanged.
- **Given** the resolved collision rules, **When** skill-enforcement globs are regenerated, **Then** django/fastapi and go/go-fiber no longer claim identical paths in a multi-stack project.
- **Given** docs changes, **When** `make docs-lint` and `uv run pytest tests/test_template_scaffold.py -q` run, **Then** both are green with new structure-spec tests.

## Work Log
- 2026-06-11 [claude]: Shipped anatomy contract (commit bcded442): docs/engineering/project-anatomy.md (top-level tree, shared/contracts cross-
