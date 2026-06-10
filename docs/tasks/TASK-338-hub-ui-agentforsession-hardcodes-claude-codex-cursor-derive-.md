---
id: TASK-338
title: "Hub UI: agentForSession hardcodes claude/codex/cursor \u2014 derive agent ids from the adapter manifest (/api/board/list agent_states keys)"
swimlane: core
kind: refactor
epic: null
labels: []
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
- src/core/board_os/hub_adapter_manifest.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
