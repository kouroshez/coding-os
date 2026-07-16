---
id: TASK-287
title: "Harden inject-mcp-caller-session.sh: jq fail-closed + WIP-cap shared-PID detection"
swimlane: core
kind: bug
epic: panel-state-isolation
labels: [state-isolation, hooks, fail-closed, concurrency, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-09
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260609-143642-c7c5
depends_on: []
blocked_by: []
references: []
---
# TASK-287: Harden inject-mcp-caller-session.sh: jq fail-closed + WIP-cap shared-PID detection

**Outcome (one sentence):** inject-mcp-caller-session.sh L31 does `command -v jq || exit 0` — a SILENT fail-open that disables per-panel MCP attribution and lets the per-session WIP cap collapse across panels (both share the MCP-server PID). Make jq-absence fail-loud (warn to stderr + diagnostic marker) instead of silent exit; if injection cannot proceed, surface it rather than silently degrading. Add detection in the WIP-cap path (board_os workflow.check_wip / mcp_tools) for an agent_session that resolved to a shared synthetic ses-<agent>-pid<server-pid>, warning instead of silently sharing the cap. Nothing silent.

## Read First
- src/core/hooks/inject-mcp-caller-session.sh
- src/core/board_os/workflow.py
- docs/engineering/state-files.md

## Repro Steps
1. Remove `jq` from PATH (simulate a host without jq).
2. Fire a PreToolUse MCP tool call so inject-mcp-caller-session.sh runs.
3. The hook hits L31 `command -v jq >/dev/null 2>&1 || exit 0` and exits 0 silently; the MCP write is attributed via the stale `.active-session` pointer. With two panels sharing the MCP-server PID, check_wip counts both under one synthetic `ses-<agent>-pid<server-pid>`.
Expected: a loud stderr warning + diagnostic marker that attribution is degraded; WIP path surfaces the shared-PID condition.
Actual: silent `exit 0`; per-panel attribution and per-session WIP cap silently collapse.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** jq is absent, or an agent_session resolves to a shared synthetic `ses-<agent>-pid<server-pid>`.
- **When** the inject hook runs / board_os check_wip counts in-progress tasks.
- **Then** the hook warns to stderr and writes a diagnostic marker instead of silently exiting, check_wip surfaces the shared-PID condition rather than silently sharing the cap, `test_inject_mcp_caller_session.py` asserts the loud behavior, and `make verify-hooks` + board_os tests are green.

## Work Log
- 2026-06-09 [claude]: Hardened inject-mcp-caller-session.sh: jq-missing now warns to stderr (debounced via persistent .mcp-attribution-degrade
