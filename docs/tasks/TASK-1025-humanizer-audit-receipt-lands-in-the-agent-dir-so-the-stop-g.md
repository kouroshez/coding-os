---
id: TASK-1025
title: "humanizer audit receipt lands in the agent dir, so the Stop gate can never be satisfied"
swimlane: core
kind: bug
epic: null
labels: [governance, hooks, ready]
status: in_progress
priority: P2
appetite: 1d
created: 2026-08-24
started: 2026-08-24
completed: null
agent_session: ses-claude-20260820-192937-ef87
depends_on: []
blocked_by: []
references: []
---
# TASK-1025: humanizer audit receipt lands in the agent dir, so the Stop gate can never be satisfied

**Outcome (one sentence):** The remediation command printed by enforce-humanizer-audit.sh actually clears the gate, so a prose turn can end after its audit.

## Read First
- src/core/hooks/cos-env.sh
- src/core/hooks/enforce-humanizer-audit.sh
- src/core/rules/transparency-banner.md

## Repro Steps
In a session where nudge-humanizer fired, run the exact command the block message prints: bash ".claude/hooks/write-state.sh" .humanizer-audit "reviewed:2". The receipt lands at .coding-os/claude/.humanizer-audit (agent dir) because .humanizer-audit is absent from COS_PER_PANEL_FILES, while the hook reads $COS_PANEL_DIR/.humanizer-audit. Re-running the hook still exits 2. Observed live on 2026-08-24.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the block message's remediation command run verbatim
  **When** the Stop hook re-runs in the same session
  **Then** it exits 0.
- **Given** the receipt is a per-turn cognitive marker
  **When** it is written
  **Then** it lands in the panel dir only, with no agent-dir fallback, per the panel-scope rule for banner-visible cognitive state.

## Work Log
- 2026-08-24 [claude]: Edit cos-env.sh
