---
id: TASK-451
title: "B-4 fix: task_outcomes.model NULL + complexity UNKNOWN on MCP completions (F16 loop starvation)"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [modularity-audit-pass3, routing, F16, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-19
started: 2026-06-19
completed: 2026-06-19
agent_session: ses-claude-20260619-063923-1c50
depends_on: []
blocked_by: []
references: []
---
# TASK-451: B-4 fix: task_outcomes.model NULL + complexity UNKNOWN on MCP completions (F16 loop starvation)

**Outcome (one sentence):** record_outcome now captures model + complexity on MCP-driven completions, feeding the multi-model routing learning loop (audit F16 phase 0). Root cause: the long-lived MCP server has no COS_PANEL_DIR/COS_AGENT_DIR but knows COS_AGENT, yet _resolve_model only searched COS_AGENT_DIR + COS_STATE_DIR (missing the <state>/<agent>/.model where the snapshot lives) and _read_gate_file only read COS_STATE_DIR/.thinking_os-gate (the gate is per-panel). Proven by the live DB: skills_used (which uses the <state>/<agent> path) was captured in 60/60 recent rows while model/complexity were NULL/UNKNOWN in 364/389. Fix adds a shared _state_search_dirs() (panel -> agent -> state/agent -> state) used by both, plus strips the ppid- id prefix the gate parser misread as the level.

## Read First
- src/core/thinking_os/record_outcome.py
- src/core/hooks/cos-env.sh
- src/core/thinking_os/server.py
- docs/engineering/modularity-audit-2026-06.md

## Repro Steps
SELECT COUNT(*), SUM(model IS NULL) FROM task_outcomes WHERE created_at > datetime('now','-7 days') — returns 60, 60 (every recent MCP completion lost model+complexity).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** COS_AGENT=claude + <state>/claude/.model present, COS_AGENT_DIR/COS_PANEL_DIR/COS_AGENT_MODEL unset (the MCP-server env) **When** _resolve_model() **Then** returns the model (was None). - **Given** <state>/claude/.thinking_os-gate = "ppid-abc COMPLICATED 3" **When** _read_gate_file() **Then** ("COMPLICATED", 3) (was treating ppid-abc as the level). - **Given** record_outcome end-to-end with those markers **When** the row is written **Then** model + complexity + dimensions are non-NULL/known.

## Work Log
- 2026-06-19 [claude]: committed 94ba0717 · 2 files
- 2026-06-19 [claude]: Edit core-loop.md.tmpl
- 2026-06-19 [claude]: Edit core-loop.md.tmpl
- 2026-06-19 [claude]: Edit session-handoff.md.tmpl
- 2026-06-19 [claude]: Edit test_all_stacks_render_smoke.py
- 2026-06-19 [claude]: commit 554825cd7a — test(golden): regenerate after hook changes (B-2 checker fix + F8 cos-env drift)
