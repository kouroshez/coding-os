---
id: TASK-144
title: "E10: path/format drift — web logs.py SSOT path + UTC since-filter + runtime_paths registers the sink"
swimlane: infra
kind: bug
epic: observability-eye
labels: [observability, drift, config, ready]
status: archive
priority: P2
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-144: E10: path/format drift — web logs.py SSOT path + UTC since-filter + runtime_paths registers the sink

**Outcome (one sentence):** web/routes/logs.py composes the jsonl path from single-sourced logging_os.config constants (no inline .coding-os / .cos.log.jsonl) and filters `since` with a UTC-correct epoch (calendar.timegm, not local mktime); runtime_paths.yaml lists .cos.log / .cos.log.jsonl so the sink is excluded from scaffold + golden + manifest scans.

## Read First
- docs/engineering/observability-eye.md
- src/core/web/routes/logs.py
- src/core/logging_os/config.py
- src/core/runtime_paths.yaml

## Repro Steps
1. In a non-UTC timezone, hit /api/logs/recent?since=30m — `time.mktime(time.strptime(<UTC ts>))` interprets the UTC timestamp as LOCAL, so the earliest-epoch cutoff is wrong by the local UTC offset and rows are mis-filtered.
2. The jsonl dir name (.coding-os) + filename (.cos.log.jsonl) are inlined in logs.py:43, duplicating the values logging_os.config owns — a rename in config silently desyncs the reader.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a project log at <root>/.coding-os/.cos.log.jsonl and a non-UTC host
- **When** /api/logs/recent resolves the path and applies a `since` filter
- **Then** the path is composed from logging_os.config.STATE_DIR_NAME + LOG_BASENAME (no inline literals), the since cutoff uses calendar.timegm (UTC-correct), runtime_paths.yaml lists both sink files, and web logs route tests + a path/TZ smoke pass

## Work Log
- 2026-06-05 [claude]: Drift fixes: logging_os.config now exposes STATE_DIR_NAME/LOG_BASENAME (single source); web/routes/logs.py composes the 
