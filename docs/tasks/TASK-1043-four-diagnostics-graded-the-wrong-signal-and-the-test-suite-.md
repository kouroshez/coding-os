---
id: TASK-1043
title: "Four diagnostics graded the wrong signal, and the test suite fed them"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-09-18
started: null
completed: 2026-09-18
agent_session: ses-claude-20260918-164827-6f4a
depends_on: []
blocked_by: []
references: []
---
# TASK-1043: Four diagnostics graded the wrong signal, and the test suite fed them

**Outcome (one sentence):** Each diagnostic grades the number its name promises, and a test run stops writing into the telemetry those diagnostics read.

## Read First
- tests/conftest.py (`_isolate_registry`)
- src/cli/doctor_checks_modules.py (`runtime.recent_errors`)
- src/core/scheduled/_nightly_index.py (`_run_graph_reindex_if_stale`)

## Repro Steps

**The shared root, found while chasing the first symptom.** `conftest`'s
`_isolate_registry` *deleted* `COS_STATE_DIR` instead of pointing it anywhere.
With it unset, `cos-env.sh` derives it from the repo root — so every hook a
test spawned logged into the live `.coding-os/`. Measured: 3,095 `rule=pr-*`
rows in `log_events` for a repo whose `git_settings.enabled` is false, 102 of
them inside one three-second burst on 2026-09-15 that was a test run.

That one leak produced three of the four symptoms:

1. **Poisoned memory.** Four `learned_patterns` ("In pr-mode projects,
   attempting `git push origin main`…", seen 21–36×) minted from those rows and
   injected into every session as guidance for a workflow this project has
   never run.
2. **`runtime.recent_errors` counts policy as fault.** It called
   `log_query(level="error")` with no `event_class` filter, though migration
   v46 added the column for exactly this — "hook BLOCKs are policy, not
   faults". Measured: 19 of the last 20 ERROR rows in 24h were policy blocks,
   flipping the check to WARN and sending the operator to `cos errors` to find
   nothing wrong.
3. **`state.size_within_budget` named a command that does not exist.** Its fix
   string said `cos brain stats` (`Error: No such command 'brain'`) and blamed
   agent memory. `cos db-stats` shows the real cause: `graph_edges_v12` at
   159,712 rows and `graph_nodes` at 80,211 — the knowledge graph IS the 326 MB.

And one independent of the leak:

4. **The nightly reindex read the wrong clock.** It gated on
   `.graph-backend.json::last_ok_at`, a backend *liveness* probe refreshed on
   every query, while `cos doctor` grades `graph.freshness` on
   `MAX(graph_nodes.updated_at)`. On 2026-09-15 nightly logged
   `skipped, fresh (38050s)` and doctor called the index stale at 121176s six
   hours later. On any project in use the probe is never 24h old, so the
   self-healing leg could not fire in the one case it exists for.

Expected: a diagnostic reads the number it claims, from data the product
produced.
Actual: three read test output, and the fourth read a different clock.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the branch-guard and shared-tree suites
**When** they run
**Then** zero new rows land in the project's `log_events`.

**Given** a window whose ERROR rows are all guardrail blocks
**When** `cos doctor` runs
**Then** `runtime.recent_errors` passes and reports the policy count
separately, rather than sending the reader to `cos errors`.

**Given** a live backend beside a graph index older than 24h
**When** the nightly leg evaluates
**Then** it reindexes — the liveness probe must not mask a stale index.

**Given** any remediation string a check prints
**When** a reader runs it verbatim
**Then** the command exists.

## Work Log
- 2026-09-18 [claude]: Status transitioned to complete via cos task-done.
