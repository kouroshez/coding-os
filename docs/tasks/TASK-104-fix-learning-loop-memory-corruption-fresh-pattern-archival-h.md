---
id: TASK-104
title: "Fix learning-loop memory corruption — fresh-pattern archival, hard-delete floor, decay race/marker, cron digest"
swimlane: core
kind: bug
epic: hook-remediation
labels: [memory, decay, learning, critical, audit-n1, ready]
status: icebox
priority: P0
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-104: Fix learning-loop memory corruption — fresh-pattern archival, hard-delete floor, decay race/marker, cron digest

**Outcome (one sentence):** Fresh learned_patterns no longer archived on first decay run (last_validated stamped on INSERT); hard-delete prune cannot erase below-floor knowledge without archived_at grace; session_enrich decay uses the same flock as nightly; decay marker path unified across launchd+hooks; cron regenerates digest.

## Read First
- src/core/thinking_os/decay.py
- src/core/thinking_os/tools/learning.py
- src/core/thinking_os/session_enrich.py
- src/core/scheduled/nightly.py

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
