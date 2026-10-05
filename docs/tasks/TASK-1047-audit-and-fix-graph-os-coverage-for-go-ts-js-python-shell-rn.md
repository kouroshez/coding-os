---
id: TASK-1047
title: "Audit and fix graph_os coverage for Go, TS, JS, Python, Shell + RN, Fiber, Astro, FastAPI"
swimlane: "graph_os"
kind: bug
epic: null
labels: [ready]
status: in_progress
priority: P1
appetite: 3d
created: 2026-10-05
started: 2026-10-04
completed: null
agent_session: ses-claude-20261004-231430-d18a
depends_on: []
blocked_by: []
references: []
---
# TASK-1047: Audit and fix graph_os coverage for Go, TS, JS, Python, Shell + RN, Fiber, Astro, FastAPI

**Outcome (one sentence):** Every confirmed defect in how graph_os indexes Go, TypeScript, JavaScript, Python and Shell — and the React Native, Go Fiber, Astro and FastAPI framework surfaces — is fixed with a regression test, one commit per fix; the audit doc answers the seven completeness questions with measured evidence.

## Read First
- docs/engineering/graph-os-polyglot-audit-2026-10-04.md
- docs/playbooks/polyglot-extractor-roadmap.md
- docs/engineering/graph_os-queries.md
- docs/engineering/graph-hallucination-cures.md

## Repro Steps
Probe each extractor with adversarial fixtures per language/framework (cross-file same-package Go calls, TS .js-suffixed ESM imports, CommonJS require, Python module-alias calls, Fiber group prefixes, FastAPI include_router prefixes, .astro files) and compare emitted nodes/edges to ground truth.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the audit doc, **When** a reviewer reads it, **Then** each of the seven questions has a yes/no/partial answer backed by a reproduced probe.
- **Given** a confirmed defect in the checklist, **When** it is fixed, **Then** a regression test fails before the fix and passes after, and the fix lands in its own commit.
- **Given** the graph_os matrix row, **When** it runs at close, **Then** `uv run --extra graph_os pytest src/core/graph_os/tests/ -q` is green and `make lint` passes on the touched files.

## Work Log
- 2026-10-05 [claude]: Plan: 7 read-only auditors (go-fiber, ts-js-rn, astro, python-fastapi, shell, cross-cutting completeness, web…
- 2026-10-05 [claude]: commit f9c306e0eb — docs(graph_os): open the polyglot audit register for Go, TS, JS, Python and Shell
- 2026-10-05 [claude]: Edit test_reindex_dispatch.py
- 2026-10-05 [claude]: Edit test_reindex_dispatch.py
- 2026-10-05 [claude]: Edit resolve.go
- 2026-10-05 [claude]: Edit _sqlite_write.py
- 2026-10-05 [claude]: Edit _sqlite_write.py
- 2026-10-05 [claude]: Edit main.go
- 2026-10-05 [claude]: Edit _reindex_layers.py
- 2026-10-05 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-05 [claude]: commit 977f2b9e4c — fix(graph_os): keep inbound cross-file edges when a file is reindexed
- 2026-10-05 [claude]: F-01 fixed (977f2b9e): per-file reindex pruned nodes before re-extract; ON DELETE CASCADE erased every inbound…
- 2026-10-05 [claude]: Edit main.go
- 2026-10-05 [claude]: Edit main.go
- 2026-10-05 [claude]: Edit test_sqlite_write_rollback.py
- 2026-10-05 [claude]: Edit _sqlite_write.py
- 2026-10-05 [claude]: Edit _sqlite_write.py
- 2026-10-05 [claude]: Edit _sqlite_write.py
- 2026-10-05 [claude]: Edit test_sqlite_write_rollback.py
- 2026-10-05 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-05 [claude]: commit 9f60c959db — fix(graph_os): stop parallel reindex workers failing files on a write race
- 2026-10-05 [claude]: Edit types.py
- 2026-10-05 [claude]: Edit types.py
- 2026-10-05 [claude]: Edit types.py
- 2026-10-05 [claude]: Edit _reindex_layers.py
- 2026-10-05 [claude]: Edit _reindex_layers.py
- 2026-10-05 [claude]: Edit graph-os-polyglot-audit-2026-10-04.md
- 2026-10-05 [claude]: commit 61d4c63d36 — fix(graph_os): prune every ID an extractor stamps so renamed TS symbols do not linger
- 2026-10-05 [claude]: Edit main.go
- 2026-10-05 [claude]: Edit main.go
- 2026-10-05 [claude]: Edit resolve_ts.py
- 2026-10-05 [claude]: Edit toolchain.py
- 2026-10-05 [claude]: Edit toolchain.py
- 2026-10-05 [claude]: Edit toolchain.py
- 2026-10-05 [claude]: Edit test_resolve_ts.py
