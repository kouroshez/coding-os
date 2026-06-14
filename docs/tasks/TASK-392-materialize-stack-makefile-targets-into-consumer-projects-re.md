---
id: TASK-392
title: "Materialize stack makefile_targets into consumer projects \u2014 render_makefile_targets has no init caller"
swimlane: infra
kind: bug
epic: J-anatomy
labels: [onboarding-program, backlog, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-11
started: 2026-06-13
completed: 2026-06-13
agent_session: ses-claude-20260613-120154-405b
depends_on: [TASK-355]
blocked_by: []
references: []
---
# TASK-392: Materialize stack makefile_targets into consumer projects — render_makefile_targets has no init caller

**Outcome (one sentence):** cos init/update writes stack-contributed make targets (e.g. lint-backend, test-backend-fastapi) into a generated include (e.g. .coding-os/Makefile.stacks) wired into the project Makefile, so the suites named in AGENTS.md actually exist as runnable targets.

## Read First
- src/cli/renderer.py (render_makefile_targets — has unit tests, zero production callers)
- src/cli/main.py (init step 9 copies Makefile.base verbatim; project Makefile is a thin include)
- src/templates/_base/Makefile.base
- docs/engineering/project-anatomy.md § Glob/verify propagation

## Repro Steps
1. `cos init --agent claude -d /tmp/p --template fastapi --no-index --no-register`
2. `grep lint-backend /tmp/p/Makefile /tmp/p/.coding-os/Makefile.base` → no hits
3. AGENTS.md TOOL_ROUTING names `lint-backend`/`test-backend`, but `make lint-backend` fails with "No rule to make target". Found while testing TASK-355 (relocated names like lint-backend-fastapi are likewise text-only).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a fastapi consumer project, **When** init (or update) runs, **Then** a generated include exposes `lint-backend`/`test-backend` and `make lint-backend` resolves.
- **Given** a relocated two-backend project (go-fiber + fastapi), **When** init runs, **Then** `lint-backend-go-fiber` and `lint-backend-fastapi` are runnable targets whose cmds cd into src/services/<id>.
- **Given** an existing project Makefile, **When** update re-renders, **Then** user-authored targets are untouched (generated include only).
- **Given** the matrix, **When** `uv run pytest tests/test_cli.py -q` runs, **Then** green.

## Work Log
- 2026-06-13 [claude]: Edit _init_helpers.py
- 2026-06-13 [claude]: Edit main.py
- 2026-06-13 [claude]: Edit main.py
- 2026-06-13 [claude]: Edit update.py
- 2026-06-13 [claude]: Edit update.py
- 2026-06-13 [claude]: Edit test_makefile_materialize.py
- 2026-06-13 [claude]: Edit test_cli.py
- 2026-06-13 [claude]: commit 90396f0823 — fix(cli): materialize stack makefile_targets into a generated include
- 2026-06-13 [claude]: Edit update.py
- 2026-06-13 [claude]: Edit test_cli.py
- 2026-06-13 [claude]: Edit update.py
- 2026-06-13 [claude]: commit 719360a2c4 — fix(update): correct base.yaml path so update materializes Makefile + AGENTS.md
- 2026-06-13 [claude]: Complete. init + update now materialize world.makefile_targets into .coding-os/Makefile.stacks and wire a -include into 
