---
id: TASK-1121
title: "fix(board): CLI and MCP attribute a task move to whichever session prompted last"
swimlane: "board_os"
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-11-24
started: 2026-11-24
completed: 2026-11-24
agent_session: ses-claude-20261123-135444-89e7
depends_on: []
blocked_by: []
references: []
---
# TASK-1121: fix(board): CLI and MCP attribute a task move to whichever session prompted last

**Outcome (one sentence):** A task created or moved from the agent's Bash shell (the `cos task-*` CLI) is attributed to the session that made the call, even while another session in the same project prompts more recently, so its board events reach that session. (Amended 2026-11-24: the MCP path stays with the `inject-mcp-caller-session` hook, because an MCP server can outlive a `/clear` and its inherited panel id may name a session that no longer prompts.)

## Read First
- src/core/board_os/_agent_runtime.py
- src/cli/_board_cli_shared.py
- src/core/thinking_os/_server_runtime.py
- docs/engineering/state-files.md

## Repro Steps
Two Claude sessions open in coding-os. Session B sends a prompt (rewrites .coding-os/claude/.active-session). Session A runs `cos task-start TASK-N` from its Bash tool: the task's agent_session is B's id and A never sees the ▶️ board event. Observed 2026-11-24: TASK-1120 started in panel 87ecf579 got ses-claude-20261124-140244-e2ad (panel f21630df).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** two panels with different session-ids and the shared pointer naming the other one, **When** the CLI resolver runs with this panel's CLAUDE_CODE_SESSION_ID, **Then** it returns this panel's session-id.
- **Given** no runtime session env (a plain shell), **When** the resolver runs, **Then** it still falls back to .active-session.
- **Given** an env panel id holding a path separator, **When** resolved, **Then** it is sanitised like `_cos_resolve_panel_id` and never reads outside `panels/`.

## Work Log
- 2026-11-24 [claude]: Fix: own_panel_session() reads the runtime's panel id (adapter.yaml runtime_session_marker env_vars, e.g.…
- 2026-11-24 [claude]: Fix: own_panel_session() reads the runtime's panel id from adapter.yaml runtime_session_marker env_vars (e.g.…
- 2026-11-24 [claude]: commit c1aec4a775 — fix(scaffold): review round 1 — remedies every gate accepts, adapter-scoped paths, missing tests
- 2026-11-24 [claude]: commit d847422e55 — fix(board): attribute a CLI or MCP task write to its own panel, not the last prompter
- 2026-11-24 [claude]: commit 8470003c29 — fix(scaffold): skip local-only state and leave every code-span form untouched
- 2026-11-24 [claude]: Fix in d847422e: own_panel_session() reads the runtime's panel id and runs before the shared .active-session in the…
- 2026-11-24 [claude]: Fix in d847422e: own_panel_session() reads the runtime's panel id and runs before the shared .active-session in the…
- 2026-11-24 [claude]: Fix in d847422e: own_panel_session() reads the runtime's panel id and runs before the shared .active-session in the…
- 2026-11-24 [claude]: commit 0bf50aeee2 — fix(board): keep the runtime-panel step in the CLI only, scoped to the detected agent
- 2026-11-24 [claude]: commit f2bc290bb9 — test(board): a panel id with a separator never reads outside panels/
- 2026-11-24 [claude]: Live: this Bash shell has CLAUDE_CODE_SESSION_ID=87ecf579..., the panel dir name
- 2026-11-24 [claude]: Live: sibling pointer named SIBLING, CLI resolver returned this session 89e7
- 2026-11-24 [claude]: Status transitioned to complete via cos task-done.
