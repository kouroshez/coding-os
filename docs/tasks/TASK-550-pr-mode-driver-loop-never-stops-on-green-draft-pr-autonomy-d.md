---
id: TASK-550
title: "pr-mode-driver loop never stops on green draft PR (autonomy=draft spin)"
swimlane: core
kind: bug
epic: pr-mode-hardening
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-550: pr-mode-driver loop never stops on green draft PR (autonomy=draft spin)

**Outcome (one sentence):** pr-mode-driver SKILL.md adds a STOP clause: a green PR that needs a human merge (autonomy=draft/degraded-no-required-check, auto_merge_armed=false) halts and surfaces to the user instead of re-polling forever.

## Read First
- src/core/skills/pr-mode-driver/SKILL.md
- tests/test_golden_parity.py

## Repro Steps
1. Consumer at autonomy_level=draft; agent runs cos pr submit (no auto-merge armed); CI goes green (ci_rollup=passing).
2. Driver follows the SKILL decision table each turn.
Expected: driver STOPs and tells the user a human merge is needed.
Actual: the `passing` row says "re-poll next turn — do nothing else"; with auto-merge never arming at draft, the agent re-polls a green PR forever.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** autonomy_level=draft, ci_rollup=passing, and cos pr submit reported merge_status in {draft, degraded-no-required-check} (auto_merge_armed=false)
- **When** the driver evaluates the loop this turn
- **Then** it STOPs and surfaces: "PR #N is green and needs a human merge (autonomy=draft) — merge it, or set autonomy_level=auto_merge in Hub Config→Git"; golden fixtures re-captured and parity tests pass

## Work Log
- 2026-06-24 [claude]: Edit SKILL.md
- 2026-06-24 [claude]: committed d19895df · 7 files
- 2026-06-24 [claude]: Status transitioned to complete via cos task-done.
