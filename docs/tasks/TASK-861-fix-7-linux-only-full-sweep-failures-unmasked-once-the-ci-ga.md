---
id: TASK-861
title: "Fix 7 Linux-only full-sweep failures unmasked once the CI gates went green"
swimlane: infra
kind: bug
epic: null
labels: [ci, linux-only, full-sweep, ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-08-03
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-861: Fix 7 Linux-only full-sweep failures unmasked once the CI gates went green

**Outcome (one sentence):** The three pytest jobs (py3.10/3.11/3.12, ubuntu) pass, turning CI Pass fully green: 7 failures that only reproduce on Linux CI are fixed with evidence from the CI environment itself (act/container repro or targeted CI debug runs), not blind patches.

## Read First
- tests/test_git_index_lock.py
- tests/test_cognition_dispatch_obs.py
- tests/test_logs_route.py
- tests/test_hub_settings_auto_spawn.py
- tests/test_panel_isolation.py
- tests/test_pre_commit_no_deadlock.py

## Repro Steps
All 7 pass on macOS (verified 2026-08-02) and fail on ubuntu-latest across py3.10/11/12 — run 30773048738. They surfaced only after this session fixed the earlier gates (ruff drift, workflow parse, openapi drift, embedding skips, golden collection, manifest pollution, registry-scope test, herestring loop, branding allowlist); the full tests/ sweep had not executed past the first gate on Linux for 40+ days.

## Acceptance (G/W/T) — *this IS the Definition of Done*
1. **Given** run 30773048738's failure list, **When** each of the 7 tests runs on ubuntu CI, **Then** it passes or carries an evidence-backed platform skip: test_stream_trace_route_registered, test_logs_route stream registration, test_git_index_lock ×2, test_gate_dedups_inflight_spawns, test_gc_reaps_orphan_panel_without_session_id, test_array_build_does_not_deadlock_on_large_list (Errno 7 Argument list too long).
2. **Given** all seven resolve, **When** CI runs on main, **Then** the CI Pass gate is green end to end.
3. **Given** every fix, **When** reviewed, **Then** each cites a Linux-side repro or CI log line — none are macOS-guessed.

## Work Log
