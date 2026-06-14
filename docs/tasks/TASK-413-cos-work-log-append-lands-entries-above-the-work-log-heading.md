---
id: TASK-413
title: "cos_work_log_append lands entries above the ## Work Log heading when the name appears in prose"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-13
started: 2026-06-13
completed: 2026-06-13
agent_session: ses-claude-20260613-135830-6a46
depends_on: []
blocked_by: []
references: []
---
# TASK-413: cos_work_log_append lands entries above the ## Work Log heading when the name appears in prose

**Outcome (one sentence):** cos_work_log_append targets the real ## Work Log heading via a line-anchored match, so entries always land under it even when the task body prose (Acceptance/Repro) mentions the literal string ## Work Log.
- 2026-06-13 [claude]: Fixed cos_work_log_append to match the ## Work Log heading line-anchored (re.search (?m)^## Work Log$) instead of substr

## Read First
- src/core/board_os/mcp_tools.py

## Repro Steps
TASK-411's Acceptance bullet #1 contains the literal `## Work Log` in backticks; cos_work_log_append used content.find("## Work Log") which matched that prose first, so 11 work-log lines (incl. the agent's per-Edit appends) landed ABOVE the real heading and the DoD emitted DOD_WORK_LOG_MISSING. Fix: re.search(r"(?m)^## Work Log[ \t]*$", content) + line-anchored next-H2 search.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a task whose Acceptance prose contains the literal `## Work Log`, **When** cos_work_log_append runs, **Then** the new entry lands under the real heading at EOF, never above it in the prose.
- **Given** a task with no Work Log heading at all, **When** append runs, **Then** a heading + entry is created at EOF (behavior unchanged).
- **Given** the change, **When** board_os work-log tests run, **Then** green (regression test added).

## Work Log
