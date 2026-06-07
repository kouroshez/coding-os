---
id: TASK-225
title: "Observability/trace scale: bounded tail-reads (256KB windows, max-N files by mtime) \u2014 no full-dir glob or whole-file load"
swimlane: core
kind: feature
epic: enterprise-scale
labels: [scale, web, observability, traces]
status: icebox
priority: P0
appetite: 2d
created: 2026-06-07
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-225: Observability/trace scale: bounded tail-reads (256KB windows, max-N files by mtime) — no full-dir glob or whole-file load

**Outcome (one sentence):** The observability/cognition endpoints never read 100% of a log/trace or glob all trace files: _read_hook_events/_read_cognition_events/get_trace/_scan_sessions tail-read bounded windows (e.g. last 256KB, last N files by mtime) with offset/cursor pagination; no whole-file load (1GB jsonl must not OOM). Verified by a 1GB trace + 10K-session dir returning bounded, fast responses. See audit-enterprise-scale-2026-06-07.md (web_routes findings, observability.py:259-265, cognition.py get_trace).

## Read First
- docs/tasks/audits/audit-enterprise-scale-2026-06-07.md
- src/core/web/routes/observability.py
- src/core/web/routes/cognition.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
