---
id: TASK-071
title: "Replace mtime polling with watchdog + asyncio pubsub for board SSE (<150ms p95)"
swimlane: core
kind: feature
epic: hub-ux-hardening
labels: [hub, realtime, sse]
status: icebox
priority: P2
appetite: "3h"
created: 2026-04-24
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-071: Replace mtime polling with watchdog + asyncio pubsub for board SSE

**Outcome (one sentence):** Board `task-updated` events fire within 150 ms p95 (down from the current ~2 s polling baseline) by replacing the mtime scan in `core/web/routes/stream.py` with a `watchdog` filesystem observer plus an in-process asyncio pubsub that MCP/board writers push directly into — and a new bench harness records the latency per event.

## Read First

- [core/web/routes/stream.py](../../core/web/routes/stream.py) — current SSE generator: lines 138–273 merge DB `task_status_history` polling with `docs/tasks/*.md` mtime polling on a `COS_WEB_SSE_POLL_MS` loop (default 2000ms).
- [core/board_os/workflow.py](../../core/board_os/workflow.py) — every `cos_task_move` / `cos_task_create` / CLI edit passes through here; ideal place to publish direct events.
- [core/thinking_os/db.py](../../core/thinking_os/db.py) — `task_status_history` append (still authoritative; we only *add* a low-latency channel).
- Session `ad8ed04b` b analysis: the DB is already authoritative and fast; the win is replacing the 2 s fallback with an event-driven channel.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** a task is moved via `cos task-move TASK-057 --to in_progress`
  **When** the SSE client is connected
  **Then** the `task-updated` event arrives at the client within **150 ms p95** (measured over 100 events in the bench harness).
- **Given** a human hand-edits `docs/tasks/TASK-057-*.md` in an editor (not via CLI — so no DB row)
  **When** the file saves
  **Then** the watchdog observer fires within 150 ms, triggers a single DB query to refresh the task row, and emits the SSE event. Debounce coalesces multiple saves within 100 ms into one event.
- **Given** the Hub daemon restarts
  **When** SSE reconnects
  **Then** history bootstrap still works via the existing `/api/stream/history?limit=20`; no events are lost (pubsub is process-local, DB remains the durable source).
- **Given** 500 simultaneous file edits (stress)
  **When** the observer fires
  **Then** CPU usage stays < 5% of one core and no event is dropped.
- **Tests:** `tests/test_board_sse_latency.py` drives the bench harness and asserts p95 ≤ 150 ms; `tests/test_sse_dedup.py` (existing) keeps passing; `tests/test_stream_fallback_poll.py` covers the scenario where watchdog fails to start (Docker, CI without FS notify permissions) and the loop falls back to poll with a WARN log.

## Implementation Notes

1. **Dependency:** add `watchdog>=4.0` to `pyproject.toml` (`rag` or a new `realtime` extra — decide during review; prefer bundling with the default Hub install).
2. **Observer:** single `BoardObserver(BaseHandler)` in `core/web/realtime.py` wired to `docs/tasks/` recursively; emits normalized events `{kind: "file-change", path, old_mtime, new_mtime}` into an `asyncio.Queue` shared with the SSE generator.
3. **Direct pubsub:** in `workflow.py`, after each state transition, push `{kind: "task-event", task_id, old, new, agent, reason, ts}` into the same queue — this is the low-latency fast path (sub-10 ms).
4. **SSE generator:** `async for event in queue` replaces the polling loop. Fall back to `COS_WEB_SSE_POLL_MS` polling only when observer initialisation raises (log WARN + metric `board_sse_fallback_poll_total`).
5. **Debounce:** a per-path timer coalesces events in a 100 ms window to avoid flooding when an editor writes atomically (write-tmp-then-rename produces multiple inotify events).
6. **Bench harness:** `scripts/bench_sse_latency.py` — spawns a client, runs 100 moves in sequence, collects ts delta, prints p50 / p95 / p99 (asserted in CI).

## Dependencies

- **Depends on:** none hard. TASK-072 Settings tab will expose the poll fallback interval once this lands.
- **Unblocks:** TASK-084 (Hooks tab live feed), TASK-087 (retrieval feedback precision bar live updates).

## Work Log
