---
id: TASK-803
title: "Wire expires_at forward \u2014 TTL stamp at capture + decay GC of expired rows + clear on enrich-promote"
swimlane: "thinking_os"
kind: feature
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-07-05
started: 2026-07-05
completed: 2026-07-05
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-803: Wire expires_at forward — TTL stamp at capture + decay GC of expired rows + clear on enrich-promote

**Outcome (one sentence):** Mechanical `changelog` observations captured from now on carry a real `expires_at` and are garbage-collected by decay once expired — wiring the dead TTL lifecycle forward, non-destructively (legacy NULL-expiry rows are untouched).

## Read First
- src/core/thinking_os/capture.py (`MECHANICAL_MEMORY_TYPE`; the INSERT cols/vals idiom at ~362)
- src/core/thinking_os/decay.py (the expired-row GC at ~287)
- src/core/thinking_os/session_observe_worker.py (item A's promote UPDATE — must clear expires_at)

## Scope (FORWARD wiring only — the owner-gated legacy sweep of the ~4566 existing rows is a separate task)
1. capture.py: `_MEMORY_TTL_DAYS` map (changelog=30, config/workflow=60, pattern=90; durable classes → None = never); stamp `expires_at` (UTC `%Y-%m-%d %H:%M:%S`, NOT isoformat) into the INSERT via the task_id conditional-append idiom.
2. decay.py: widen the GC to `WHERE expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP` (drop the `memory_type='working'` gate) — a no-op today (0 rows have expires_at), live once capture stamps.
3. session_observe_worker.py (A): on the changelog→discovery promote, also `SET expires_at = NULL` so an enriched, durable row is not GC'd on the changelog TTL.
4. Read-side exclusion NOT needed: item B already excludes changelog from recall, and changelog is the only TTL'd class capture produces.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a fresh changelog observation is captured,
- **When** it is inserted,
- **Then** `expires_at ≈ now + 30d`; decay deletes an observation whose `expires_at` is in the past but spares one with NULL expiry (so the legacy corpus is safe); an A-promoted discovery row has `expires_at = NULL`; and the thinking_os matrix + `server.py --test` stay green.

## Work Log
- 2026-07-05 [claude]: Edit capture.py
- 2026-07-05 [claude]: Edit capture.py
- 2026-07-05 [claude]: Edit capture.py
- 2026-07-05 [claude]: Edit decay.py
- 2026-07-05 [claude]: Edit session_observe_worker.py
- 2026-07-05 [claude]: Edit test_session.py
- 2026-07-05 [claude]: F-forward wired: capture stamps expires_at (via _MEMORY_TTL_DAYS: changelog=30d, config/workflow=60d, pattern=90d;…
- 2026-07-05 [claude]: commit 61982216a0 — feat(memory): wire expires_at forward — TTL stamp at capture + decay GC of expired rows
- 2026-07-05 [claude]: Status transitioned to complete via cos task-done.
