---
id: TASK-225
title: "Observability/trace scale: bounded tail-reads (256KB windows, max-N files by mtime) \u2014 no full-dir glob or whole-file load"
swimlane: core
kind: feature
epic: enterprise-scale
labels: [scale, web, observability, traces, ready]
status: complete
priority: P0
appetite: 2d
created: 2026-06-07
started: 2026-06-07
completed: 2026-06-07
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-225: Observability/trace scale: bounded tail-reads (256KB windows, max-N files by mtime) — no full-dir glob or whole-file load

**Outcome (one sentence):** The observability/cognition endpoints never read 100% of a log/trace or glob all trace files: _read_hook_events/_read_cognition_events/get_trace/_scan_sessions tail-read bounded windows (e.g. last 256KB, last N files by mtime) with offset/cursor pagination; no whole-file load (1GB jsonl must not OOM). Verified by a 1GB trace + 10K-session dir returning bounded, fast responses.

## Read First
- src/core/web/routes/observability.py
- src/core/web/routes/cognition.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a 1GB trace jsonl and a directory with 10K session/trace files.
- **When** the observability + cognition endpoints read hook events, cognition events, a trace, or scan sessions.
- **Then** reads are bounded (last ~256KB window / last N files by mtime) with offset/cursor pagination, no whole-file load and no full-dir glob; verified by fast, bounded-memory responses on the 1GB/10K fixture (no OOM, flat latency as files grow).

## Work Log
- 2026-06-07 [claude]: committed fa360556: src/core/web/routes/_bounded_read.py, src/core/web/routes/cognition.py, src/core/web/routes/observab
- 2026-06-07 [claude]: committed fa360556: new _bounded_read (tail_text/tail_lines/newest_files); observability _scan_sessions/_read_hook_event
- 2026-06-07 [claude]: Status transitioned to complete via cos task-done.
