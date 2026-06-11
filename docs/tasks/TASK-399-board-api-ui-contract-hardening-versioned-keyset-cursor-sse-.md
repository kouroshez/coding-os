---
id: TASK-399
title: "board API/UI contract hardening \u2014 versioned keyset cursor, SSE status field normalization, list error envelope"
swimlane: core
kind: bug
epic: null
labels: [task-system-review, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-11
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-399: board API/UI contract hardening — versioned keyset cursor, SSE status field normalization, list error envelope

**Outcome (one sentence):** Three contract-drift risks closed: _keyset_column_page stops positional row[12]/row[0] indexing (named row factory + cursor version prefix), stream.py file-watch events emit new_status (not bare status) so useBoardStream drops its silent ?? fallbacks, and /api/board/list returns a proper unwrap() error envelope instead of a 400 with partially-enriched data; load-more pagination state survives an SSE bump.

## Read First
- src/core/board_os/mcp_tools.py
- src/core/web/routes/board.py
- src/core/web/routes/stream.py
- src/core/web/ui/src/features/cos-board/useBoardStream.ts
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx

## Repro Steps
1. Add a column to _BOARD_SELECT before completed_at — keyset cursors decode against last[12]/last[0] positions (mcp_tools.py ~1024-1031) and silently corrupt pagination.
2. Trigger a file-watch task event — stream.py emits bare `status` while DB-poll events emit `new_status`; useBoardStream papers over it with `data.current_status ?? data.status ?? null`.
3. Force an error from /api/board/list — route returns 400 with a partially-enriched envelope instead of unwrap()'s error shape.
Expected: schema-versioned named-column cursor; one SSE payload contract; uniform error envelope.
Actual: positional indexing, dual field names hidden by ?? fallbacks, inconsistent error path; load-more pages also reset on every SSE bump (CosBoardPage setExtra({})).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a reordered _BOARD_SELECT, **When** an old cursor arrives, **Then** it is rejected by version prefix instead of decoding garbage.
- **Given** any task-updated SSE event (poll or file-watch), **When** the UI parses it, **Then** `new_status` is always present and the `?? data.status` fallback is deleted.
- **Given** a failing board list call, **When** the route errors, **Then** the response is the standard fail envelope via unwrap() and the UI handles it; load-more state survives an SSE bump.

## Work Log
