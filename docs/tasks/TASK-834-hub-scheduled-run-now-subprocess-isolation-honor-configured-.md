---
id: TASK-834
title: "Hub scheduled run-now subprocess isolation + honor configured hour (audit backlog)"
swimlane: core
kind: bug
epic: null
labels: [hub, audit, backlog, project-scope, ready]
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
1. Start the Hub from the coding-os dir: `cos hub start --port 9188`.
2. In a loop, curl a scoped read for project B: `while true; do curl -s http://127.0.0.1:9188/api/p/cos-website/board/list >/dev/null; done`.
3. Concurrently trigger a run-now for project A: `curl -X POST http://127.0.0.1:9188/api/scheduled/run/streamos`.
Expected: project B's requests always resolve cos-website's DB.
Actual: while run_project runs, nightly._run_reclaim / _run_dep_reconcile set os.environ["COS_PROJECT_ROOT"]=streamos process-wide, so a concurrent B request can resolve streamos (env is process-global, not per-request).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a Hub POST /api/scheduled/run/{slug} is running **When** another /api/p/<other>/ request is in flight during nightly maintenance **Then** the concurrent request's project scope is not corrupted (run the per-slug job in a subprocess like _run_graph_reindex_if_stale so no os.environ mutation touches the live worker).
- **Given** an installed cron with a configured hour **When** the panel renders next_run_at **Then** it reflects the installed schedule, not a hardcoded hour=3.
- **Given** a browser log beacon (POST /api/logs/client) under an /api/p/<slug>/ scope **When** it is recorded **Then** it lands in the active project's sink, and path resolution delegates to logging_os.config.jsonl_log_path().
- **When** the scheduled + logs route tests run **Then** they pass.

## Work Log
