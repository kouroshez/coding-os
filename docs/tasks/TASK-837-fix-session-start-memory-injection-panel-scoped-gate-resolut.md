---
id: TASK-837
title: "fix session-start memory injection: panel-scoped gate resolution in session_enrich"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-07-17
started: 2026-07-17
completed: 2026-07-17
agent_session: ses-claude-20260717-014556-89d0
depends_on: []
blocked_by: []
references: []
---
# TASK-837: fix session-start memory injection: panel-scoped gate resolution in session_enrich


**Outcome (one sentence):** session_enrich resolves the complexity gate from the panel dir (via the canonical record_outcome resolver), so agent_metrics records real complexity and the enrichment observer can spawn — closing root-cause cluster D (dead injection) from the memory audit.

## Read First
- src/core/thinking_os/session_enrich.py
- src/core/thinking_os/record_outcome.py
- docs/engineering/state-files.md

## Repro Steps
Write 'ses-x COMPLICATED 3' to $COS_PANEL_DIR/.thinking_os-gate; run session_enrich.py; observe agent_metrics.complexity='UNKNOWN' because it reads $COS_STATE_DIR/.thinking_os-gate which does not exist.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a `.thinking_os-gate` marker written at `$COS_PANEL_DIR` containing "ses-x COMPLICATED 3"
**When** `session_enrich.py` runs at the Stop hook
**Then** it reads complexity COMPLICATED (not UNKNOWN), `agent_metrics.complexity` reflects it, the `_gate_complexity` duplicate is removed in favor of `record_outcome._read_gate_file`, and `test_session.py` has a regression test that fails on the old COS_STATE_DIR-only path.

## Work Log
- 2026-07-17 [claude]: Edit session_enrich.py
- 2026-07-17 [claude]: Edit session_enrich.py
- 2026-07-17 [claude]: Edit session_enrich.py
- 2026-07-17 [claude]: Edit session_enrich.py
- 2026-07-17 [claude]: Edit session_enrich.py
- 2026-07-17 [claude]: Edit session_enrich.py
- 2026-07-17 [claude]: Fixed: session_enrich read .thinking_os-gate from COS_STATE_DIR (wrong dir) → complexity always UNKNOWN. Extracted…
- 2026-07-17 [claude]: committed a3170dae · 4 files
