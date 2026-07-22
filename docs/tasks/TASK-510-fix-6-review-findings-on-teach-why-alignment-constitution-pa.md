---
id: TASK-510
title: "Fix 6 review findings on teach-why-alignment (constitution path, slice guards, CLEAR-1 glob, bypass scope, dup BLOCK)"
swimlane: core
kind: bug
epic: teach-why-alignment
labels: [teach-why, review-fix, hooks, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-21
started: 2026-06-21
completed: 2026-06-21
agent_session: ses-system-auto-archive
depends_on: [TASK-497]
blocked_by: []
references: []
---
# TASK-510: Fix 6 review findings on teach-why-alignment (constitution path, slice guards, CLEAR-1 glob, bypass scope, dup BLOCK)

**Outcome (one sentence):** Fix 6 real defects found by the max-effort review of the teach-why-alignment epic (the review's verify phase was rate-limited, so findings were re-verified manually against the code; commit-message capture findings F6/F10/F15 were confirmed working and left as-is). server.py: resolve constitution path via database.project_root() instead of Path(__file__).parents[3] (which resolves outside the project for consumer installs) AND assert non-empty slice CONTENT, not just marker presence. session-context.sh: truncate .clear1-bypass-log on SessionStart:startup so bypasses=N is genuinely per-session (was lifetime panel count) AND only inject the slice when BOTH SLICE markers are present (a missing SLICE:END made sed dump the rest of the file). write-state.sh: anchor the CLEAR-1 match so "CLEAR 10"/"CLEAR 15 X" no longer false-log as bypasses. enforce-task-transition.sh: lead the block with WHY (not a second BLOCKED — the helper already emits one) and drop the pointless allow-path stderr re-emit.

## Read First
- src/core/thinking_os/server.py
- src/core/thinking_os/database.py
- src/core/hooks/session-context.sh
- src/core/hooks/write-state.sh
- src/core/hooks/enforce-task-transition.sh

## Repro Steps
1) Run cos_health from a consumer-layout install → constitution.present=false at a path outside the project (parents[3] bug). 2) write-state.sh .thinking_os-gate "CLEAR 10" → .clear1-bypass-log gains a false entry; banner shows bypasses=1. 3) Remove SLICE:END from constitution.md, fire SessionStart → whole file tail injected. 4) Hand-edit a task status → enforce-task-transition prints two BLOCKED lines.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a consumer-layout install, **When** cos_health runs, **Then** the constitution path resolves via database.project_root() (not parents[3]).
- **Given** constitution.md with markers but empty content, **When** cos_health runs, **Then** slice content is reported absent (markers alone do not pass).
- **Given** a self-issued "CLEAR 10" gate write, **When** write-state runs, **Then** it is NOT logged as a CLEAR-1 bypass.
- **Given** a new SessionStart:startup, **When** the banner renders, **Then** bypasses=N counts only the current session (log truncated at startup).
- **Given** constitution.md missing SLICE:END, **When** session-context runs, **Then** the slice is not injected (no unbounded dump).
- **Given** a hand-edited task status, **When** enforce-task-transition blocks, **Then** exactly one BLOCKED line appears, preceded by a WHY; verify GREEN: make verify-hooks + thinking_os matrix + server --test.

## Work Log
- 2026-06-21 [claude]: Edit write-state.sh
- 2026-06-21 [claude]: Edit enforce-task-transition.sh
- 2026-06-21 [claude]: Edit session-context.sh
- 2026-06-21 [claude]: Edit session-context.sh
- 2026-06-21 [claude]: Edit server.py
- 2026-06-21 [claude]: Edit server.py
- 2026-06-21 [claude]: commit 85d8cbe1db — fix(core): harden teach-why epic per review (path resolver, slice guards, CLEAR-1 glob, dup BLOCK)
- 2026-06-21 [claude]: Fixed 6 manually-verified review findings (verify phase was rate-limited). server.py: constitution path via…
