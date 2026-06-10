---
id: TASK-338
title: "Hub UI: agentForSession hardcodes claude/codex/cursor \u2014 derive agent ids from the adapter manifest (/api/board/list agent_states keys)"
swimlane: core
kind: refactor
epic: null
labels: [ready]
status: icebox
priority: P3
appetite: 2h
created: 2026-06-10
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-338: Hub UI: agentForSession hardcodes claude/codex/cursor — derive agent ids from the adapter manifest (/api/board/list agent_states keys)

**Outcome (one sentence):** useBoardStream.agentForSession (and its kindColors consumers) resolve agent ids data-driven from the adapter manifest instead of a hardcoded string-sniff list, so a new adapter shows correctly on the board feed with zero UI edits.

## Read First
- src/core/web/ui/src/features/cos-board/useBoardStream.ts
- src/core/board_os/hub_adapter_manifest.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the adapter manifest lists the installed agents, **When** the board feed renders an event whose `agent_session` contains any manifest agent id, **Then** the agent chip/color comes from manifest data — `agentForSession` holds no literal agent-name list.
- **Given** a hypothetical new adapter id (e.g. `gemini`) present in the manifest, **When** its session emits a board event, **Then** the feed attributes it to that agent (not `human`) with zero UI code edits — covered by a unit test that injects a fake manifest id.
- **Given** the existing UI suite, **When** `npx vitest run` executes, **Then** all tests pass.

## Work Log
- 2026-06-10 [claude]: committed 5931c037: src/core/board_os/mcp_tools.py, src/core/board_os/tests/test_mcp_tools.py, src/core/skills/task-driv
