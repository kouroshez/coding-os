---
id: TASK-648
title: "fastapi async drift \u2014 pytest-asyncio absent + sample uses sync TestClient vs documented async-first"
swimlane: templates
kind: bug
epic: stack-completeness-v2
labels: [fastapi, drift, wave-1, testing, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-30
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-648: fastapi async drift — pytest-asyncio absent + sample uses sync TestClient vs documented async-first

**Outcome (one sentence):** The fastapi scaffold declares pytest-asyncio (asyncio_mode=auto) and ships an async-first sample endpoint + test, matching the python-fastapi SKILL's documented async-first architecture, so the shipped sample no longer teaches a pattern the docs forbid and async tests actually run green.

## Read First
- src/templates/fastapi/skills/python-fastapi/SKILL.md
- src/templates/fastapi/scaffold/src/backend/pyproject.toml

## Repro Steps
1. Open src/templates/fastapi/scaffold/src/backend/pyproject.toml — no pytest-asyncio dependency and no asyncio_mode config.
2. Open the sample test — it uses a sync TestClient against sync endpoints, while src/templates/fastapi/skills/python-fastapi/SKILL.md mandates async-first.
Expected: scaffold + sample consistent with the documented async-first architecture.
Actual: a consumer writing an async test per the SKILL hits "coroutine was never awaited" / no asyncio plugin; the shipped sample contradicts the shipped guidance.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the fastapi scaffold, **When** `cd src/backend && pytest -q` runs, **Then** async tests are collected via asyncio_mode=auto and pass.
- **Given** the sample endpoint + test, **When** read, **Then** both are async, consistent with the python-fastapi SKILL.
- **Given** the template suite, **When** `uv run pytest tests/test_template_scaffold.py -q` runs, **Then** green; and `uv run cos stack-lint fastapi` PASS.

## Work Log
