---
id: TASK-529
title: "pr-mode has no autonomous red-CI loop \u2014 add cos pr status CI-rollup + a driver skill that polls\u2192heal/cleanup"
swimlane: infra
kind: feature
epic: pr-mode-hardening
labels: [pr-mode, autonomy, self-heal, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-23
started: 2026-06-23
completed: 2026-06-23
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-529: pr-mode has no autonomous red-CI loop — add cos pr status CI-rollup + a driver skill that polls→heal/cleanup

**Outcome (one sentence):** The 'if CI red, diagnose+fix+retry' loop the spec promises becomes real and runnable by a non-expert consumer: cos pr status returns the PR state + statusCheckRollup/mergeStateStatus (merged|red|pending) as a single signal, and a shipped pr-mode driver skill/command encodes the poll→branch(merged→cleanup | red→heal+fix+repush | pending→wait) decision so the agent is told how to drive the loop instead of having to remember to call the blind cos pr heal counter.

## Read First
- src/cli/pr_commands.py
- src/core/skills/
- docs/playbooks/pr-workflow.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an open agent PR **When** `cos pr status` runs **Then** it returns a single field reporting merged|red|pending from statusCheckRollup/mergeStateStatus.
- **Given** a red CI **When** the driver skill runs **Then** it charges the heal budget and emits the fix+repush step; **When** the budget is exhausted **Then** it escalates the task to blocked.
- **Given** a merged PR **When** the driver runs **Then** it triggers cleanup.
- **And** `uv run pytest tests/test_cli.py -q` is green and the skill is registered.

## Work Log
- 2026-06-24 [claude]: Deliberation: split into (1) a pure _rollup_state(pr)->merged|red|pending|passing|closed|none mapper +…
- 2026-06-24 [claude]: Edit pr-workflow.md
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit test_cli.py
- 2026-06-24 [claude]: Edit SKILL.md
- 2026-06-24 [claude]: commit 14c9689811 — feat(pr-mode): cos pr status CI rollup + pr-mode-driver skill for the autonomous loop
- 2026-06-24 [claude]: Status transitioned to complete via cos task-done.
