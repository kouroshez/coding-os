---
id: TASK-671
title: "Redundant-run metric \u2014 record verify-suite re-run rate to an append-only metrics table for retro"
swimlane: "board_os"
kind: feature
epic: test-discipline
labels: [tests, metrics, retro, ready]
status: archive
priority: P3
appetite: 1d
created: 2026-06-30
started: null
completed: null
agent_session: ses-claude-20260630-011740-9a32
depends_on: []
blocked_by: []
references: []
---
# TASK-671: Redundant-run metric — record verify-suite re-run rate to an append-only metrics table for retro

**Outcome (one sentence):** A redundant-run metric records, to an append-only metrics table created by a new vN+1 migration, how often a verify-suite run is deduped or re-requested on an unchanged tree, so retro can quantify over-testing via cos_metric_trend instead of guessing — fire-and-forget, never blocking the run.

## Read First
- src/core/hooks/test-governor.sh
- src/core/thinking_os/tools/metrics.py
- src/core/thinking_os/database.py
- docs/engineering/test-governance.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a deduped verify run, **When** test-governor records it, **Then** a redundant-run event is persisted to the new append-only metrics table via a vN+1 migration that never edits a past migration.
- **Given** recorded redundant-run events, **When** cos_metric_trend is queried, **Then** the over-testing rate is reportable for a retro window.
- **Given** the metric write path, **When** it fails, **Then** it is fire-and-forget and never blocks the test run.

## Work Log
