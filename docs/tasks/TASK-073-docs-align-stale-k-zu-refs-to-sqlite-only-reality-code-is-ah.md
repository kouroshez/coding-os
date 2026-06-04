---
id: TASK-073
title: "docs: align stale Kùzu refs to SQLite-only reality (code is ahead; docs follow)"
swimlane: docs
kind: docs
epic: null
labels: [graph_os, kuzu, alignment]
status: in_progress
priority: P3
appetite: "2h"
created: 2026-06-04
started: 2026-06-03
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-073: docs: align stale Kùzu refs to SQLite-only reality (code is ahead; docs follow)

**Outcome (one sentence):** Living docs that imply Kùzu is a live/configurable graph backend are corrected to SQLite-only (Kùzu retired 2026-05-18; backend_fallback reserved/always-false; 21 cos_graph_* tools). Historical/retirement records (ADR-0002, retirement notes, legacy-dir cleanup) and accurate code comments are KEPT. Scope: docs only — graph code is correct and authoritative.

## Read First
- docs/adr/0002-retire-kuzu-backend.md
- src/core/skills/graph-explorer/SKILL.md
- docs/engineering/graph_os-queries.md

## Work Log
