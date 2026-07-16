---
id: TASK-829
title: "Surface per-session hook-block trend in cos retro (prose-layer health KPI)"
swimlane: "board_os"
kind: feature
epic: null
labels: [context-economy, metrics, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-07-16
started: null
completed: null
agent_session: null
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
