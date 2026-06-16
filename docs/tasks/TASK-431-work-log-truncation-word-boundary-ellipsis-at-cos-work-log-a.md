---
id: TASK-431
title: "Work-log truncation: word-boundary ellipsis at cos_work_log_append funnel + count-first post-commit summary"
swimlane: infra
kind: bug
epic: null
labels: [board_os, work-log, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-16
started: 2026-06-15
completed: 2026-06-15
agent_session: ses-claude-20260615-011729-aaaf
depends_on: []
blocked_by: []
references: []
---
# TASK-431: Work-log truncation: word-boundary ellipsis at cos_work_log_append funnel + count-first post-commit summary

**Outcome (one sentence):** Every work-log note >=120 chars trims at a word boundary with a single ellipsis char instead of a raw mid-word cut, and the post-commit summary front-loads the file count so the load-bearing datum survives any trim. The trim lives at the shared cos_work_log_append funnel (mcp_tools.py:2507) so it covers every persona/caller at once (Hub-chat MCP, human git-hook, agent path).

## Read First
- src/core/board_os/mcp_tools.py
- src/scripts/_post_commit_body.sh
- tests/test_post_commit_tasklog.py
- docs/tasks/TASK-175-commit-to-task-log-write-back-via-post-commit-hook.md

## Repro Steps
TASK-428 work-log line 47 = 'committed 5f8b7ed0: ...src/cli/main.py, s' — chopped mid-path at char 120 by mcp_tools.py:2507 raw [:120] slice; the '(+N files)' count from _post_commit_body.sh:35-40 destroyed. No ellipsis marks the loss.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a >120-char summary, **When** cos_work_log_append records it, **Then** the stored line trims at the last space within budget and ends with an ellipsis, len <= 120, no mid-word cut.
**Given** a commit touching N code files, **When** _post_commit_body.sh runs, **Then** it writes 'committed <sha> · <N> file(s)' (count-first, no enumerated file list) and the existing sha-based dedup still fires.
**Given** the change, **When** src/core/board_os/tests/test_mcp_tools.py and tests/test_post_commit_tasklog.py run, **Then** all pass (the :59 file-name assertion updated to the count form; a new funnel-ellipsis test added).

## Work Log
- 2026-06-16 [claude]: Edit mcp_tools.py
- 2026-06-16 [claude]: Edit mcp_tools.py
- 2026-06-16 [claude]: Edit _post_commit_body.sh
- 2026-06-16 [claude]: Edit test_post_commit_tasklog.py
- 2026-06-16 [claude]: Edit test_mcp_tools.py
- 2026-06-16 [claude]: Status transitioned to complete via cos task-done.
