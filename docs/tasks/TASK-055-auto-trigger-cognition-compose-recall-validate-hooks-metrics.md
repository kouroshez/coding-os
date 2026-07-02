---
id: TASK-055
title: "Auto-trigger cognition: compose+recall+validate hooks, metrics variance, memory UI (TASK-048 deferred R1)"
swimlane: thinking_os
kind: feature
epic: null
labels: []
status: archive
priority: P1
appetite: "1d"
created: 2026-06-01
started: 2026-06-01
completed: 2026-06-01
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-055: Auto-trigger cognition: compose+recall+validate hooks, metrics variance, memory UI (TASK-048 deferred R1)

**Outcome (one sentence):** The cognition read-arcs fire mechanically: roles auto-compose+surface on COMPLICATED+, recall injects in Orient, validate closes on task-done, metrics carry variance, learned patterns visible in Hub.

## Read First

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a session with a COMPLICATED/COMPLEX `.thinking_os-gate`, **When** the next prompt fires `auto-compose-roles.sh`, **Then** `.roles`/`.role` are stamped and the composed lead role appears in the session banner (`roles=`).
- **Given** the same gate, **When** the hook runs, **Then** `cos_learn_suggest` results are written to `.learn-suggestions` so `remind-learn-validate` has input and the Orient recall arc fires.
- **Given** a SessionStart, **When** `session-context.sh` runs, **Then** `digest.md` is regenerated (not just printed) so the always-active working-memory digest is fresh.
- **Given** a session that ends with a `completion_gap` observation, **When** `session_enrich.py` records `agent_metrics`, **Then** `outcome='partial'` (not the old hardcoded `success`) and `duration_ms` reflects the real observation time-span.
- **Given** the learned_patterns table, **When** a user opens Hub → Diagnostics → Memory, **Then** patterns render with confidence / trust_tier / decay / validated / used.
- **Given** a malformed `formula_id`, **When** `cos_supervise_record_output` is called, **Then** it returns `fail("validation", …)` instead of persisting the garbage.
- **Given** the matrix verification per changed layer, **Then** all targeted suites pass.

## Work Log
- 2026-06-01 [claude]: Groups A–E landed. A: auto-compose-roles.sh + _helpers/auto_compose.py + thinking_os/roles_state.py (shared .roles writer; cognition.py uses it); banner roles= field. B: auto_compose also runs learn_suggest→.learn-suggestions; _helpers/digest_regen.py regenerates digest.md at SessionStart. C: session_enrich.py derives real outcome (completion_gap→partial) + duration from observation span. D: web/routes/patterns.py + Hub MemoryPage.tsx (Diagnostics→Memory). E: formula_id allow-list guard in cos_supervise_record_output. Verified: thinking_os 1210/0, web 55/0, learning 59/0, verify-hooks clean, ui-build clean, MCP self-test PASS. Docs aligned: transparency-banner (roles field), Rule 15 (auto-fire), AGENTS.md hook counts 83/77/28. ⚠️ user must restart MCP server for in-memory cognition.py/session changes. Commits pending: a peer session's git (PID 68590) deadlocked in its pre-commit hook held .git/index.lock; per user, left peer untouched.
