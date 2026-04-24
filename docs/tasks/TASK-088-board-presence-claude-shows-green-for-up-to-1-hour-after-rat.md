---
id: TASK-088
title: "Board presence: Claude shows green for up to 1 hour after rate-limit kill (dead PID + stale heartbeat stays 'active')"
swimlane: core
kind: bug
epic: hub-ux-hardening
labels: [hub, presence, live-agents]
status: testing
priority: P1
appetite: "1h"
created: 2026-04-24
started: 2026-04-24
completed: null
agent_session: ses-cursor-20260424-192151-c03d
depends_on: []
blocked_by: []
references: []
---

# TASK-088: Board presence — dead-PID session stays GREEN for up to 1 hour

**Outcome (one sentence):** When a Claude (or Codex / Cursor) session is killed by rate-limit, crash, or `kill -9` — so no graceful `SessionEnd`/`Stop` hook ever fires — the live-agents pill flips to OFFLINE within the `_ACTIVE_WINDOW_SECS` (30 s), not after the full `_PRESENT_WINDOW_SECS` (1 hour) as today.

## Reproduction (observed this session)

- `.coding-os/claude/sessions/ses-claude-20260424-181007-2af6.json`: `pid=53480` (confirmed dead via `ps -p 53480`), `ended_at=null`, `last_tool_at` 46 minutes ago.
- Hub renders the live `claude` pill in GREEN (`state == "active"` / `"present"`) because the two failing branches in `_presence_state()` don't gate on PID liveness tightly enough:
  1. **Branch B** ("user turn in flight") matches whenever `last_prompt_at` is within 1 h and `last_stop_at` is null — true for Claude because it was killed before emitting `Stop`. Returns `"active"` **without even checking PID**.
  2. **Branch C / dead-PID fallback** accepts any heartbeat within the 1 h `_PRESENT_WINDOW_SECS` as "recent", so an agent that died 45 min ago stays PRESENT for another 15 min.
- Meanwhile `Codex` shows RED because `.coding-os/codex/sessions/` does not exist on disk (Codex CLI never actually ran against this project today) — that is **not** this bug's scope; it is a separate infra gap about whether Codex-via-Cursor should count toward `codex` presence (follow-up).

## Read First

- [core/web/routes/board.py](../../core/web/routes/board.py) — `_presence_state()` (lines ~116–189), window constants (81–83), `_pid_alive` helper.
- [core/hooks/agent-presence.sh](../../core/hooks/agent-presence.sh) — the hook that writes per-session files (note: no invariant that `SessionEnd` always fires; rate-limit kill / SIGKILL skips it).
- [tests/test_agent_presence_state.py](../../tests/test_agent_presence_state.py) — existing coverage; the `test_dead_pid_with_recent_heartbeat_is_active` test must keep passing (Cursor subprocess-rotation tolerance) BUT with the clock bounded to the ACTIVE window, not PRESENT.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** a presence file with `pid=<dead>`, `ended_at=null`, `last_tool_at = now - 5s`
  **When** `_presence_state(agent)` is called
  **Then** it returns `"active"` — preserves the subprocess-rotation tolerance (Cursor / Claude Code VSCode rotate pids between hook fires).
- **Given** a presence file with `pid=<dead>`, `ended_at=null`, `last_tool_at = now - 120s` (past ACTIVE window)
  **When** `_presence_state` is called
  **Then** it returns `"offline"` — no longer PRESENT/ACTIVE just because the heartbeat was within 1 h.
- **Given** a presence file with `pid=<dead>`, `ended_at=null`, `last_prompt_at = now - 600s`, `last_stop_at = null` (the "rate-limit killed mid-turn" shape)
  **When** `_presence_state` is called
  **Then** it returns `"offline"` (not `"active"` as today).
- **Given** a presence file with `pid=<alive>`, `last_tool_at = now - 300s` (idle)
  **When** `_presence_state` is called
  **Then** it returns `"present"` — unchanged; alive-PID idle stays visible.
- **Tests:** two new cases in `tests/test_agent_presence_state.py` cover the killed-mid-turn shape and the "dead pid + stale heartbeat past ACTIVE" shape; full `tests/test_agent_presence_state.py` stays green.

## Implementation Notes

1. **Branch B fix:** tighten the `last_prompt` → ACTIVE path to require the prompt within `_ACTIVE_WINDOW_SECS` AND the PID alive. The 1 h tolerance was too forgiving.
2. **Branch C fix:** in the dead-PID fallback, the "recent heartbeat" check must use `_ACTIVE_WINDOW_SECS` (subprocess-rotation tolerance), not `_PRESENT_WINDOW_SECS`. Keeping the name but swapping the window.
3. **Bonus GC cleanup (cheap, do it):** in `agent-presence.sh` GC block, also drop files where `pid` is dead AND `(last_tool_at | last_prompt_at) > _PRESENT_WINDOW_SECS` — keeps the sessions dir from accumulating ghosts forever when `ended_at` is never written.
4. **No schema changes** — logic-only, no DB, no migration.
5. **Document** the expected flip-to-OFFLINE timeline in `core/web/routes/board.py::_presence_state` docstring so the next reader doesn't reintroduce the regression.

## Follow-up (out of scope)

- "Codex via Cursor should count as Codex presence" — design decision: do we track by *runtime* (cursor) or *model* (codex)? Not in this task.

## Work Log

- 2026-04-24 [cursor/claude-opus-4-7]: Implemented — `_presence_state()` now requires
  PID liveness once past the ACTIVE window (30 s).  Branch B ("turn in flight →
  ACTIVE") tightened to ACTIVE window as well.  Two new regression tests cover
  the killed-mid-turn + stale-heartbeat shapes; existing
  `test_dead_pid_with_recent_heartbeat_is_active` preserves the Cursor
  subprocess-rotation tolerance.  Real-world verification on the current
  project: claude → offline (rate-limit kill), codex → offline, cursor →
  active.  12/12 presence tests green; adjacent `test_agent_presence_visuals`
  + `test_sdk_presence` unaffected.
