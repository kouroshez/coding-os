---
id: TASK-340
title: "link-commit-to-task mislinks under concurrent sessions + silently drops the work-log append"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: archive
priority: P1
appetite: 2h
created: 2026-06-10
started: 2026-06-10
completed: 2026-06-10
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-340: link-commit-to-task mislinks under concurrent sessions + silently drops the work-log append

**Outcome (one sentence):** Commit-to-task links are correct and durable under concurrent sessions: the sha comes from THIS command's git output (never a rev-parse of a racing HEAD), the work-log append runs synchronously so it cannot be killed mid-flight, and a .task-current owned by another panel's session is never trusted.

## Read First
- src/core/hooks/link-commit-to-task.sh
- src/core/hooks/_helpers/work_log_append.py
- src/core/board_os/mcp_tools.py

## Repro Steps
1. Session A (task TASK-337 in_progress) runs `git commit` in background; session B (TASK-336) commits ~30s later, before A's pre-commit hooks finish.
2. Observe `.coding-os/.hooks.log` 2026-06-10 15:59: A's hook links B's sha 2421b203 to TASK-337; B's hook links A's sha 35304d9b to TASK-336 (rev-parse HEAD race).
3. Inspect both task Work Logs: the hook-appended lines are absent entirely — the backgrounded `python3 work_log_append.py … &` dies when the hook process exits.
Expected: each task logs exactly its own commit sha, durably.
Actual: cross-linked shas in the hook log, nothing on disk, panel history shows no commits.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** two sessions committing within the same second, **When** the PostToolUse hook fires, **Then** each task's Work Log gets only its own session's sha (sha parsed from the tool_response commit output, not HEAD).
- **Given** a successful link, **When** the hook exits, **Then** the work-log line is already on disk (synchronous append) — verified by a synthetic-payload smoke test.
- **Given** a .task-current stamped by a different session id, **When** the hook runs, **Then** it does not link (ownership check).
- **Given** make verify-hooks, **When** run, **Then** green.

## Work Log
- 2026-06-10 [claude]: Edit capture-work-log.sh
- 2026-06-10 [claude]: Edit link-commit-to-task.sh
- 2026-06-10 [claude]: commit 3a28a783 — fix(hooks): commit-to-task links survive macOS + concurrent sessions
- 2026-06-10 [claude]: commit dac4509de1 — fix(hooks): widen commit-link fallback window to 5min — slow pre/post-commit hooks outlive 20s
- 2026-06-10 [claude]: Status transitioned to complete via cos task-done.
