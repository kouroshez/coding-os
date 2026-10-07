---
id: TASK-1055
title: "Turn main CI green: fix the 13 mypy errors that pushed the ratchet to 1090 > 1078"
swimlane: "graph_os"
kind: bug
epic: null
labels: [ci, mypy, ready]
status: complete
priority: P0
appetite: 1d
created: 2026-10-07
started: 2026-10-07
completed: 2026-10-07
agent_session: ses-claude-20261004-231430-d18a
depends_on: []
blocked_by: []
references: []
---
# TASK-1055: Turn main CI green: fix the 13 mypy errors that pushed the ratchet to 1090 > 1078

**Outcome (one sentence):** The CI mypy ratchet (venv synced with --extra rag only, py3.12) counts at most 1078 on main, so Lint passes, the pytest jobs it gated run again, and release PR #107 can merge.

## Read First
- src/scripts/mypy_ratchet.py
- docs/engineering/ci-gates.md

## Repro Steps
CI runs 37672518310 (main 3e76132e) and 37672674975 (PR #107) failed with `mypy-ratchet: FAIL — 1090 errors > baseline 1078 (+12)`, and every test job was skipped. Reproduce: UV_PROJECT_ENVIRONMENT=<tmp> uv sync --python 3.12 --extra rag; uv run mypy --exclude /tests/ src/core/thinking_os src/core/board_os src/core/graph_os → 1090. Last green c2e0d3b9 counts 1075.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a CI-equivalent venv (--extra rag, py3.12), **When** the ratchet scope is counted, **Then** it is <= 1078.
- **Given** the fixes, **When** the graph_os suite runs, **Then** it passes with no behaviour change.
- **Given** the push, **When** CI runs on main, **Then** Lint and every test job are green.

## Work Log
- 2026-10-07 [claude]: Edit _contracts_file_routes.py
- 2026-10-07 [claude]: Edit _sqlite_links_go_implements.py
- 2026-10-07 [claude]: Edit _md_mdx.py
- 2026-10-07 [claude]: Edit _go_calls.py
- 2026-10-07 [claude]: Edit _undefined_python.py
- 2026-10-07 [claude]: Edit _undefined_python.py
- 2026-10-07 [claude]: Edit _sqlite_write.py
- 2026-10-07 [claude]: Edit _sqlite_write.py
- 2026-10-07 [claude]: Edit _graph_undefined.py
- 2026-10-07 [claude]: Edit _md_mdx.py
- 2026-10-07 [claude]: Reproduced CI's 1090 exactly in a --extra rag py3.12 venv (local env reads lower because graph_os extra is…
- 2026-10-07 [claude]: commit d284e3b780 — fix(graph_os): clear the 13 mypy errors that held CI red and guard ast.TypeAlias on py3.10
- 2026-10-07 [claude]: Status transitioned to complete via cos task-done.
