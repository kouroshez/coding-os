---
id: TASK-051
title: "Fix Claude presence: agent-presence.sh exits when panel session-id missing (TASK-035 regression)"
swimlane: core
kind: bug
epic: null
labels: []
status: complete
priority: P2
appetite: "1d"
created: 2026-05-31
started: 2026-05-31
completed: 2026-05-31
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: ["TASK-035"]
---
# TASK-051: Fix Claude presence: agent-presence.sh exits when panel session-id missing (TASK-035 regression)

**Outcome (one sentence):** `agent-presence.sh` writes a presence file for the live interactive session again so the Hub HUD shows Claude green/active — by falling back to the agent-level `session-id` when the per-panel `$COS_SESSION_FILE` is absent.

## Read First
- src/core/hooks/agent-presence.sh — the writer (exited early at the panel session-id check)
- src/core/hooks/cos-env.sh — `COS_SESSION_FILE` repointed to `$COS_PANEL_DIR` (TASK-035)
- src/core/board_os/presence.py + src/core/web/routes/presence.py — the reader chain (agent-level `sessions/`)

## Repro Steps
1. Run an interactive Claude Code session on this repo; open the Hub HUD (`/api/presence/now`).
2. Observe `.coding-os/claude/panels/ppid-<hash>/` has `heartbeat` but no `session-id`; the live `session-id` is only under UUID panels (seeded by session-context.sh upgrade).
3. `agent-presence.sh` resolves the `ppid-<hash>` panel → `$COS_SESSION_FILE` missing → `exit 0` before writing presence.

Expected: live session has `.coding-os/claude/sessions/<sid>.json` with fresh `last_tool_at` + live pid → HUD dot green/active.
Actual: only stale `ses-claude-sdk-F99-*` files (all `ended`) → `agent_state`=offline → grey dot.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an interactive session whose panel `session-id` is unseeded but agent-level `session-id` exists,
- **When** any tool-use hook fires `agent-presence.sh`,
- **Then** a fresh `$COS_AGENT_DIR/sessions/<agent-session-id>.json` is written and `/api/presence/now` reports the agent as `active`/`working`/`present` (not `offline`); `make verify-hooks` green.

## Work Log
- 2026-05-31 [claude]: Status transitioned to complete via cos task-done.
