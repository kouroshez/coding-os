---
id: TASK-104
title: "Fix learning-loop memory corruption — fresh-pattern archival, hard-delete floor, decay race/marker, cron digest"
swimlane: core
kind: bug
epic: hook-remediation
labels: [memory, decay, learning, critical, audit-n1, ready]
status: complete
priority: P0
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-104: Fix learning-loop memory corruption — fresh-pattern archival, hard-delete floor, decay race/marker, cron digest

**Outcome (one sentence):** Fresh learned_patterns no longer archived on first decay run (last_validated stamped on INSERT); hard-delete prune cannot erase below-floor knowledge without an archived_at grace; session_enrich decay uses the same flock as nightly; decay marker path unified across launchd+hooks; cron regenerates digest.

## Read First
- src/core/thinking_os/decay.py
- src/core/thinking_os/tools/learning.py
- src/core/thinking_os/session_enrich.py
- src/core/scheduled/nightly.py

## Repro Steps
1. learn_extract INSERTs a new learned_pattern (confidence 0.5, times_validated 0); its last_validated / last_accessed_at are NULL.
2. run_decay (decay.py) executes once (nightly, or session_enrich on a >7d marker).
Expected: a fresh, never-validated pattern keeps its confidence (age ~0) and stays active.
Actual: _days_since(NULL)→None → months=(None or 999)/30≈33.3 → decay_confidence collapses 0.5→~0.018 → clamped to CONFIDENCE_FLOOR 0.1 → promoted_to='archived' on the FIRST decay run; if dormant >90d the prune hard-DELETEs it. The loop destroys its own freshly mined knowledge.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a freshly extracted learned_pattern (times_validated=0, just INSERTed)
- **When** run_decay executes for the first time after creation
- **Then** the pattern is NOT archived (last_validated stamped at creation → age≈0 → no age-decay); re-extracting an archived pattern revives it (promoted_to=NULL); session_enrich decay holds the same flock as nightly; the decay marker resolves to one project-scoped path across nightly+hooks; `test_decay` + `test_learning` pass.

## Work Log
- 2026-06-05 [claude]: 1a+1c DONE (commit d69a52b): _upsert_pattern stamps last_validated/last_accessed_at on INSERT (fresh pattern age 0, no f
- 2026-06-05 [claude]: N1 COMPLETE 1a-1g: fresh-pattern preservation (d69a52b), archived_at grace v33 (568c4d9), shared run_decay_locked flock+
