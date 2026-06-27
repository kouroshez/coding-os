---
id: TASK-605
title: "bootable scaffold: fastapi + django + python (manifest + entrypoint + sample test + verify block)"
swimlane: templates
kind: feature
epic: stack-factory-v2
labels: []
status: icebox
priority: P2
appetite: 2d
created: 2026-06-27
started: null
completed: null
agent_session: null
depends_on: [TASK-602]
blocked_by: []
references: []
---

# TASK-605: bootable scaffold: fastapi + django + python (manifest + entrypoint + sample test + verify block)

**Outcome (one sentence):** The three python-family stacks become runnable seeds (today .gitkeep/docs-only — verified P0). Each gets a pyproject.toml + entrypoint skeleton + a sample test pulling the T4 (TASK-602) ruff/pytest config, and django/fastapi gain the `verify:` per-glob block they currently lack.

## Read First
- src/templates/fastapi/stack.yaml
- src/templates/django/stack.yaml
- src/templates/nestjs/scaffold/

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** fastapi, **When** `cos init` then `make lint-backend`/`make test-backend`/run, **Then** they pass on a pyproject.toml + app/main.py (FastAPI health) + tests/test_health.py + .env.example.
**Given** django, **When** the same, **Then** pyproject + manage.py + settings skeleton + a sample test run, and the `verify:` per-glob block is present in stack.yaml.
**Given** python (plain), **When** the same, **Then** either it ships a runnable pyproject seed OR is explicitly marked library-exempt in stack-lint with the decision recorded.
**Then** `uv run pytest tests/test_template_scaffold.py -q` is green.

## Work Log
