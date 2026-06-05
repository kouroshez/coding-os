---
id: TASK-109
title: "Fix memory-load correctness — digest-on-compact, learn_suggest relevance, marker≠search, banner TTL staleness"
swimlane: core
kind: bug
epic: hook-remediation
labels: [memory, session, hooks, banner, audit-n5]
status: icebox
priority: P1
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-109: Fix memory-load correctness — digest-on-compact, learn_suggest relevance, marker≠search, banner TTL staleness

**Outcome (one sentence):** Digest re-injected on compact/resume; learn_suggest uses complexity+domain (relevant recall); banner _read_state applies the 120-min TTL and marks stale skill/gate/task; cos_search defaults to min_confidence=0.3/since_days=180.

## Read First
- src/core/hooks/session-context.sh
- src/core/thinking_os/tools/learning.py
- src/core/hooks/enforce-memory-check.sh

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
