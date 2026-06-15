---
id: TASK-388
title: "Clean eject \u2014 `cos eject` removes coding-os from a project keeping code/docs"
swimlane: cli
kind: feature
epic: H-lifecycle
labels: [backlog, onboarding-program, ready]
status: complete
priority: P3
appetite: 1d
created: 2026-06-11
started: 2026-06-14
completed: 2026-06-14
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-388: Clean eject — `cos eject` removes coding-os from a project keeping code/docs

**Outcome (one sentence):** `cos eject` cleanly detaches a consumer project: removes symlinks/state/adapter wiring, keeps user code and docs, prints a summary of what was removed and kept.

## Read First
- src/cli/update.py (asset manifest — knows exactly what coding-os installed)
- src/cli/registry.py
- src/core/scripts/install-adapter.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an initialized consumer project, **When** `cos eject --yes` runs, **Then** coding-os symlinks, .coding-os/ state and adapter wiring are removed, user code + docs remain byte-identical, and a removed/kept summary is printed; the project is deregistered from the global registry.
- **Given** user-authored (non-symlink) files inside the agent dir, **When** eject runs, **Then** they are preserved in place or moved to a visible backup — never silently deleted.
- **Given** an already-ejected (or never-initialized) project, **When** eject runs again, **Then** it exits 0 as a no-op with a clear message.
- **Given** the matrix, **When** the targeted eject test class in tests/test_cli.py runs, **Then** green.

## Work Log
- 2026-06-15 [claude]: committed fec8dedd: README.md, docs/architecture/meta-project.md, src/cli/main.py, src/cli/materialize_file.py, tests/te
