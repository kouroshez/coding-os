---
id: TASK-829
title: "Surface per-session hook-block trend in cos retro (prose-layer health KPI)"
swimlane: "board_os"
kind: feature
epic: null
labels: [context-economy, metrics, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-07-16
started: 2026-08-02
completed: 2026-08-02
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-829: Surface per-session hook-block trend in cos retro (prose-layer health KPI)

**Outcome (one sentence):** Block counts per hook per session already exist in the hooks log; retro should show the trend (blocks/session over the period) so a falling rate proves rules are being internalized and a rising rate flags prose-layer failure. Uses existing log data only — no new capture.

## Read First
- src/core/board_os/
- src/core/hooks/registry.yaml
- docs/engineering/hooks-reference.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a period with hook-block events, **When** cos retro runs, **Then** it reports blocks/session per top-blocking hook and the trend vs the prior period. **Given** zero block events, **When** retro runs, **Then** the section is omitted (no noise).

## Work Log
- 2026-08-02 [claude]: Edit mcp_tools.py
- 2026-08-02 [claude]: Edit mcp_tools.py
- 2026-08-02 [claude]: Edit test_mcp_tools.py
- 2026-08-02 [claude]: commit 46ce11bf66 — feat(board): hook-block trend KPI in cos retro (blocks/session vs prior period)
- 2026-08-02 [claude]: Implemented _hook_block_trend over log_events (durable block sink, no new capture): blocks/session, prior-period…
