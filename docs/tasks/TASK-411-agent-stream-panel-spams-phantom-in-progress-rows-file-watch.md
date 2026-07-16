---
id: TASK-411
title: "AGENT STREAM panel spams phantom \"? -> in_progress\" rows \u2014 file-watch emits on every work-log mtime bump; live events not deduped"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-13
started: 2026-06-13
completed: 2026-06-13
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-411: AGENT STREAM panel spams phantom "? -> in_progress" rows — file-watch emits on every work-log mtime bump; live events not deduped

**Outcome (one sentence):** The Hub board AGENT STREAM panel shows one row per real status transition; a work-log append (or any non-status edit) to a task .md produces zero phantom transition rows, and identical consecutive live task-updated events are collapsed instead of stacking.

## Read First
- src/core/web/routes/stream.py
- src/core/web/ui/src/features/cos-board/useBoardStream.ts
- src/core/hooks/capture-work-log.sh

## Repro Steps
In the Hub board with a task in_progress, perform several code Edits in a session. Each Edit fires capture-work-log.sh which appends a "[agent]: Edit <file>" line to the active task .md, bumping its mtime. The SSE file-watch branch in stream.py treats every mtime change as a transition and emits old_status=None/new_status=in_progress/source=file. The panel renders one "TASK-NNN ? -> in_progress" row per append (random newId() ⇒ no dedup), stacking 7+ identical rows.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a task whose `## Work Log` is appended while its `status:` frontmatter is unchanged, **When** `_poll_tick` runs, **Then** no file-watch `task-updated` event is emitted for that task (status-watermark guard).
- **Given** a real status change in task frontmatter not backed by a DB row, **When** `_poll_tick` runs, **Then** exactly one file-watch `task-updated` event is emitted.
- **Given** two identical consecutive live `task-updated` events (same taskId + newStatus + source) within a short window, **When** rendered in AGENT STREAM, **Then** only one row is kept.
- **Given** the changes, **When** the stream test suite runs (`uv run pytest tests/ -k stream`), **Then** green.
- 2026-06-13 [claude]: Edit hub-architecture.md
- 2026-06-13 [claude]: Edit stream.py
- 2026-06-13 [claude]: Edit stream.py
- 2026-06-13 [claude]: Edit useBoardStream.ts
- 2026-06-13 [claude]: Edit useBoardStream.ts
- 2026-06-13 [claude]: Edit useBoardStream.ts
- 2026-06-13 [claude]: Edit test_stream_dedup.py
- 2026-06-13 [claude]: Edit useBoardStream.ts
- 2026-06-13 [claude]: Edit useBoardStream.test.ts
- 2026-06-13 [claude]: Edit useBoardStream.test.ts
- 2026-06-13 [claude]: Fixed: stream.py file-watch now keeps a per-file status watermark (last_status) and emits task-updated only when status:

## Work Log
- 2026-06-13 [claude]: Edit mcp_tools.py
- 2026-06-13 [claude]: Edit test_mcp_tools.py
- 2026-06-14 [claude]: committed 1d5011e4: src/core/web/routes/stream.py, src/core/web/ui/src/features/cos-board/useBoardStream.test.ts, src/co
