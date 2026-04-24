---
id: TASK-065
title: "Fix agent detection priority in board commands"
swimlane: cli
kind: bug
epic: null
labels: []
status: complete
priority: P2
appetite: "1d"
created: 2026-04-24
started: 2026-04-24
completed: 2026-04-24
agent_session: ses-cursor-20260424-061051-8b12
depends_on: []
blocked_by: []
references: []
---
# TASK-065: Fix agent detection priority in board commands

**Outcome (one sentence):** Runtime detection priority now resolves as `claude -> codex -> cursor`, with regression tests proving precedence across overlapping env markers.

## Read First
- `cli/board_commands.py` (`_detect_agent_runtime`, `_agent_session_id`)
- `tests/test_board_commands_agent_detect.py`
- `AGENTS.md` (task shape + verification expectations)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** overlapping runtime markers for Claude, Codex, and Cursor
- **When** `_detect_agent_runtime()` evaluates env markers
- **Then** precedence is enforced as `claude` first, then `codex`, then `cursor`
- **And** explicit `COS_AGENT` override still wins over marker-based detection
- **And** existing board/presence/stream related tests remain green

## Work Log
- 2026-04-24 [cursor]: Created task via `cos task-create` and moved to `in_progress`.
- 2026-04-24 [cursor]: Updated `cli/board_commands.py` to use explicit ordered runtime priority (`claude`, `codex`, `cursor`) with deterministic fallback ordering for additional adapters.
- 2026-04-24 [cursor]: Added regression tests in `tests/test_board_commands_agent_detect.py`:
  - `test_priority_prefers_claude_over_codex_and_cursor`
  - `test_priority_prefers_codex_over_cursor`
- 2026-04-24 [cursor]: Verified with `PYTHONPATH=. uv run --extra rag --with aiohttp --with pytest-asyncio pytest tests/test_board_commands_agent_detect.py tests/test_agent_presence_state.py tests/test_stream_dedup.py core/board_os/tests/test_workflow.py core/thinking_os/tests/test_routing.py -q` (93 passed).
- 2026-04-24 [cursor]: Status transitioned to complete via cos task-done.
