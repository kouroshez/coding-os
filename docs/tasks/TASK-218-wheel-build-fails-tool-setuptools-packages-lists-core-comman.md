---
id: TASK-218
title: "Wheel build fails \u2014 tool.setuptools.packages lists core.commands (a data-only .md dir, no __init__) so wheel-from-sdist breaks, blocking pip/PyPI"
swimlane: infra
kind: bug
epic: null
labels: [packaging, release, discovered-during-TASK-077, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-06
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260606-135311-dd32
depends_on: []
blocked_by: []
references: []
---
# TASK-218: Wheel build fails — tool.setuptools.packages lists core.commands (a data-only .md dir, no __init__) so wheel-from-sdist breaks, blocking pip/PyPI

**Outcome (one sentence):** `uv build` produces BOTH a valid sdist AND a wheel without the `package directory does not exist` error, by dropping the data-only dirs (core.commands, core.hooks) from `[tool.setuptools.packages]`. Deeper publish-readiness (shipping .md/.sh/skills/rules/templates as wheel data + runtime resource resolution so a pip-installed `cos` finds them) is carved to a follow-up task, sequenced with the PyPI publish (TASK-077).

## Read First
- pyproject.toml
- docs/governance/release-process.md
- src/core/commands/

## Repro Steps
1. Run `uv build` (builds sdist, then wheel-from-sdist).
Expected: both `dist/*.tar.gz` and `dist/*.whl` produced, exit 0.
Actual (before fix): wheel-from-sdist aborts with `error: package directory 'src/core/commands' does not exist` — setuptools lists `core.commands` (10 .md, no `__init__.py`) as an import package; the `__init__`-less dir is dropped from the sdist, then the in-sdist wheel build cannot find it.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `[tool.setuptools.packages]` no longer lists the data-only dirs `core.commands` / `core.hooks` (verified: nothing imports them as modules; `_enforce_scaffold_boundary.py` runs as a subprocess, not an import).
- **When** `uv build` runs end-to-end.
- **Then** it exits 0 and emits both a `.tar.gz` and a `py3-none-any.whl`, with no "package directory does not exist" error.

## Work Log
- 2026-06-07 [claude]: Dropped data-only dirs core.commands + core.hooks from pyproject [tool.setuptools.packages] (verified nothing imports th
- 2026-06-07 [claude]: committed 8d0dbba7: pyproject.toml
