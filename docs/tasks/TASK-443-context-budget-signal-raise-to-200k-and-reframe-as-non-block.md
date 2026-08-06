---
id: TASK-443
title: "Context-budget signal: raise to 200K and reframe as non-blocking user reminder (governance, preserve agent autonomy)"
swimlane: infra
kind: bug
epic: null
labels: [governance, docs-update, context-budget, autonomy, dogfood, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-16
started: 2026-06-16
completed: 2026-06-16
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-443: Context-budget signal: raise to 200K and reframe as non-blocking user reminder (governance, preserve agent autonomy)

**Outcome (one sentence):** The context-budget marker becomes an informational, non-blocking user reminder at a 200K threshold; the agent never halts autonomous multi-task work because of it. /compact is the in-task tool; /clear is the user's choice between unrelated tasks.

## Read First
- docs/playbooks/doctor-checks.md
- src/core/rules/transparency-banner.md

## Repro Steps
In an autonomous run over multiple related icebox tasks, the agent completes 1-2 tasks then stops and recommends /clear because the ctx>150K marker + transparency-banner.md rule instruct it to "recommend a fresh session instead of pulling the next task" — even when remaining tasks are related. This breaks autonomy.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a session over 200K context, **When** the banner renders, **Then** it shows an informational ℹ️ ctx marker and the agent keeps pulling related/queued tasks without stopping.
- **Given** transparency-banner.md, **When** an agent reads it, **Then** it states the marker is a user signal (not a stop directive) and names /compact as the in-task tool.
- **Given** COS_CONTEXT_BUDGET is unset, **When** the helper runs, **Then** the threshold defaults to 200000 in context_budget.py and doctor_tokens.py.
- **Given** make verify-hooks and pytest tests/test_cli.py, **When** run, **Then** both pass.

## Work Log
- 2026-06-16 [claude]: Edit transparency-banner.md
- 2026-06-16 [claude]: Edit session-context.sh
- 2026-06-16 [claude]: Edit session-context.sh
- 2026-06-16 [claude]: Edit context_budget.py
- 2026-06-16 [claude]: Edit context_budget.py
- 2026-06-16 [claude]: Edit doctor_tokens.py
- 2026-06-16 [claude]: Edit doctor_tokens.py
- 2026-06-16 [claude]: Edit doctor-checks.md
- 2026-06-16 [claude]: Edit doctor-checks.md
- 2026-06-16 [claude]: Raised COS_CONTEXT_BUDGET default 150K→200K and reframed the banner ctx marker from a ⚠️ "/clear after this task"…
- 2026-06-16 [claude]: committed cdddc529 · 25 files
