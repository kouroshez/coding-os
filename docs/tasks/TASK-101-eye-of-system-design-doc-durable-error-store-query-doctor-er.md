---
id: TASK-101
title: "Eye-of-system design doc — durable error store + query + doctor + error→bug pipeline + capture adoption (SSOT for observability-eye epic)"
swimlane: infra
kind: docs
epic: observability-eye
labels: [observability, logging_os, error-pipeline, epic-anchor, ready]
status: complete
priority: P1
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-101: Eye-of-system design doc — durable error store + query + doctor + error→bug pipeline + capture adoption (SSOT for observability-eye epic)

**Outcome (one sentence):** A single design doc (docs/engineering/observability-eye.md) specifies the enterprise "eye": every error captured (no silent failures), durably stored (v32 log_events in coding-os.db, WARN+), queryable via cos_log_query (MCP) + cos errors (CLI), visible in cos doctor + Hub Errors panel, and recurring errors auto-filed as fingerprint-deduped board bug tasks (FATAL→emergency, ERROR→threshold). This doc is the contract every E1–E13 code task anchors to.

## Read First
- docs/engineering/logging_os.md
- src/core/logging_os/sinks.py
- src/core/thinking_os/tools/audit.py
- src/core/scheduled/nightly.py

## Work Log
- 2026-06-05 [claude]: Wrote docs/engineering/observability-eye.md — SSOT for the eye: architecture+data-flow, capture discipline (§1), v32 log
