---
id: TASK-834
title: "Hub scheduled run-now subprocess isolation + honor configured hour (audit backlog)"
swimlane: core
kind: bug
epic: null
labels: [hub, audit, backlog, project-scope]
status: icebox
priority: P2
appetite: 1d
created: 2026-07-17
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-834: Hub scheduled run-now subprocess isolation + honor configured hour (audit backlog)

**Outcome (one sentence):** Hub-invoked nightly run-now stops mutating process-global os.environ[COS_PROJECT_ROOT] (nightly _run_reclaim/_run_dep_reconcile) — race with concurrent scoped requests; run per-slug in a subprocess like _run_graph_reindex_if_stale. _next_run_at honors the installed plist hour (not hardcoded 3) and per-project hour semantics are resolved. logs.py POST /client write-side routes into the active project's sink, and path resolution delegates to logging_os.config.jsonl_log_path().

## Read First
- src/core/web/routes/scheduled.py
- src/core/scheduled/nightly.py
- src/core/web/routes/logs.py

## Repro Steps
1. (fill in: exact steps to reproduce)
2. ...
Expected: ...
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
