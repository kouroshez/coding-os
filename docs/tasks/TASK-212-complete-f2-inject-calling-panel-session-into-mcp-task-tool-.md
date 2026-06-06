---
id: TASK-212
title: "Complete F2 \u2014 inject calling-panel session into MCP task-tool args so concurrent-panel attribution is exact"
swimlane: core
kind: feature
epic: agent-hub
labels: [hooks, concurrency, mcp, attribution, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-06
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260605-233300-41f3
depends_on: []
blocked_by: []
references: []
---
# TASK-212: Complete F2 — inject calling-panel session into MCP task-tool args so concurrent-panel attribution is exact

**Outcome (one sentence):** A fail-open PreToolUse hook (`inject-mcp-caller-session.sh`) injects the calling panel's coding-os session-id (read from `$COS_SESSION_FILE`) into the args of attribution-critical MCP task tools (cos_task_move, cos_task_create, cos_work_log_append) via `hookSpecificOutput.updatedInput`, so the long-lived **panel-blind** MCP server attributes each write to the REAL calling panel instead of the last-writer-wins `.active-session` pointer — closing the ROOT-1 cluster (mis-attribution, false WIP-cap block, reclaim owner-mismatch, banner≠DB) for the Claude path and completing the half of F2 that `state-files.md` and `agent-hub-orchestration.md` documented as deferred. No Python signature change is needed — the `agent_session` params already exist (F2).

## Background / Repro
1. Two concurrent Claude panels (same agent, one repo) each call cos_task_move via the ONE shared MCP server.
2. The server has no `$COS_PANEL_DIR`; resolve_agent_session falls to the agent-global `.active-session` pointer, which session-context.sh overwrites every prompt (last-writer-wins).
3. Panel A's move is stamped with whichever panel prompted most recently → per-session WIP counts it against the wrong session (live-observed: a legitimate task-start was BLOCKED `WIP cap 1/1` although the panel owned 0 in_progress), reclaim's `owner in active` skips a dead panel's zombie, and the banner (strict-panel) disagrees with the DB (pointer).
Expected: each MCP task write is attributed to the panel that actually issued it.
Actual: attributed to the last panel that submitted a prompt.

## Read First
- src/core/hooks/branch-guard.sh (output-contract + physical-resolution patterns)
- src/core/board_os/_agent_runtime.py (resolve_agent_session order — explicit arg wins)
- src/core/hooks/registry.yaml (registration SSOT)
- src/adapters/claude/adapter.yaml (hook_capabilities.PreToolUse — needs MCP matchers)
- docs/engineering/state-files.md (§ .active-session caveat — flip "deferred" → implemented)
- docs/engineering/agent-hub-orchestration.md (§1/§2 F2)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an MCP task tool call (cos_task_move) with no explicit `agent_session` in its args, invoked from a panel whose `$COS_SESSION_FILE` holds `ses-claude-…X`
- **When** the inject-mcp-caller-session PreToolUse hook runs on that call
- **Then** it emits `hookSpecificOutput.updatedInput` equal to the original tool_input plus `agent_session=ses-claude-…X` (merge, no other field changed); when the caller already passed a non-empty `agent_session` it emits NOTHING (no override); when the panel session cannot be resolved or jq is unavailable it emits NOTHING and exits 0 (fail-open, status quo); the hook is registered in registry.yaml + rendered into the Claude adapter (matchers added to adapter.yaml hook_capabilities + `make regen-adapter-templates`); a unit test covers inject / no-override / fail-open; `make verify-hooks` is green; the deferred-note in state-files.md is updated to reflect the implemented bridge.

## Work Log
- 2026-06-06 [claude]: committed f0384989: docs/engineering/state-files.md, src/adapters/claude/adapter.yaml, src/adapters/claude/settings.temp
- 2026-06-06 [claude]: Shipped (commit f0384989): inject-mcp-caller-session.sh + registry + claude adapter.yaml matchers + settings.template.js
