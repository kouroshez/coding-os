---
id: TASK-362
title: "Init job tracking \u2014 SSE progress phases, log streaming, cancel, rollback report, funnel metrics"
swimlane: core
kind: feature
epic: B-onboarding
labels: [wave-2, onboarding-program, ready]
status: testing
priority: P0
appetite: 2d
created: 2026-06-11
started: 2026-06-11
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: [TASK-358]
blocked_by: []
references: []
---
# TASK-362: Init job tracking — SSE progress phases, log streaming, cancel, rollback report, funnel metrics

**Outcome (one sentence):** POST /api/hub/registry/init becomes job-based: returns job_id, streams phase progress + live init log over SSE (including an "agent is processing your description" phase), supports cancel, reports rollback/cleanup on partial failure, and emits funnel counters to /api/metrics.

## Read First
- src/core/web/routes/hub.py
- src/core/web/routes/stream.py
- src/core/web/routes/metrics.py
- src/core/web/ui/src/pages/HubHome.tsx

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a create request, **When** init starts, **Then** the response returns a job_id immediately and SSE delivers ordered phase events (validate → scaffold → adapters → docs-seed → register) plus incremental log lines until a terminal succeeded/failed/cancelled event.
- **Given** a running job, **When** cancel is requested, **Then** the subprocess terminates, partial scaffold cleanup runs, and the terminal event reports {cancelled, cleanup:{removed_dir}} — UI returns to an actionable state.
- **Given** a browser refresh mid-init, **When** the client reconnects with the job_id, **Then** current phase + buffered log replay correctly (job state survives the request lifecycle).
- **Given** /api/metrics, **When** jobs run, **Then** counters for started/succeeded/failed/cancelled increment (funnel observability) and route tests cover all terminal paths.

## Work Log
- 2026-06-11 [claude]: IMPL DONE (parked in testing, batch 2) — src/core/web/init_jobs.py: thread-safe in-process job registry wrapping the cos
