---
id: TASK-112
title: "Data-driven adapter detection — cos-env.sh runtime markers, doctor loaders, drop speculative GEMINI literals, .sh hardcode test"
swimlane: infra
kind: refactor
epic: hook-remediation
labels: [adapter, data-driven, cli, audit-n8, ready]
status: archive
priority: P2
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-112: Data-driven adapter detection — cos-env.sh runtime markers, doctor loaders, drop speculative GEMINI literals, .sh hardcode test

**Outcome (one sentence):** doctor's MCP loader stops silently skipping Cursor (cursor_mcp_json now maps to the Claude JSON loader), and cos-env drops speculative GEMINI_/ANTHROPIC_ session vars; the fully-data-driven cos-env agent-detection rewrite is refiled as TASK-155.

## Read First
- src/cli/doctor.py
- src/core/hooks/cos-env.sh
- src/adapters/cursor/adapter.yaml

## Repro Steps
1. Run `cos doctor` under Cursor: the `mcp.actually_launches` diagnostic is silently skipped because `cursor_mcp_json` (cursor adapter.yaml's mcp_launch.loader) is absent from doctor's `loader_fns` dict → `spec.loader not in loader_fns: continue`.
2. cos-env's panel-session-marker loop lists `GEMINI_SESSION_ID`/`ANTHROPIC_SESSION_ID` — speculative vars no shipping adapter exports.
Expected: Cursor MCP diagnostic runs; no speculative literals.
Actual: Cursor skipped; dead speculative vars.

## Acceptance (G/W/T)
- **Given** a project with `.cursor/mcp.json` (mcpServers.coding-os), **When** doctor loads the MCP launch config for agent=cursor, **Then** it resolves the command via `_load_claude_json` (no silent skip).
- **Given** cos-env's session-marker loop, **When** it resolves the panel id, **Then** it iterates only real adapter vars (claude/cursor/codex), not GEMINI_/ANTHROPIC_.
- **Given** the fully-data-driven detection goal (8a/8c), **When** scoped, **Then** it is refiled as TASK-155 (regen-generated snippet from adapter.yaml — too risky for cos-env hot path at audit-stream tail).

## Work Log
- 2026-06-05 [claude]: 8b mapped cursor_mcp_json→_load_claude_json in doctor loader_fns (Cursor MCP diagnostic no longer silently skipped); 8d 
