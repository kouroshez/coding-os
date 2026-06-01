---
id: TASK-052
title: "Hub HUD detail: read task/skill/gate newest-across-panels + fix .active-skill name + ppid prefix strip"
swimlane: core
kind: bug
epic: null
labels: []
status: complete
priority: P2
appetite: "1d"
created: 2026-06-01
started: 2026-06-01
completed: 2026-06-01
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: ["TASK-035", "TASK-051"]
---
# TASK-052: Hub HUD detail: read task/skill/gate newest-across-panels + fix .active-skill name + ppid prefix strip

**Outcome (one sentence):** The Hub HUD popover shows the live agent's current task/skill/gate again — `presence.py::_agent_runtime` reads each marker as the newest copy across `agent_dir` + all `panels/*/`, reads the correct `.active-skill` filename, and strips `ppid-`/UUID prefixes (not just `ses-`).

## Read First
- src/core/web/routes/presence.py — `_agent_runtime` + `_strip_session_prefix` (the reader)
- src/core/hooks/cos-env.sh — `COS_PER_PANEL_FILES` (markers are panel-level post-TASK-035)
- src/core/web/ui/src/layout/LiveStatus.tsx — consumer (reads agents[].task/skill_active/gate)

## Repro Steps
1. Open Hub HUD popover for the live Claude session.
2. `presence.py` reads agent-level `.task-current`/`.thinking_os-gate`/`.skill-active`; post-TASK-035 those are panel-level (scattered across `ppid-*` panels), so agent-level holds stale fossils.

Expected: HUD shows current task/skill/gate.
Actual: stale task (`"ppid-f343dff2 TASK-048"`, prefix leaked), `skill_active: null` always (wrong filename `.skill-active` vs `.active-skill`).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the live session's markers live in per-panel dirs with a `ppid-`/`ses-` prefix,
- **When** `/api/presence/now` builds the claude runtime snapshot,
- **Then** `task`/`skill_active`/`gate` reflect the newest marker across panels with the id-prefix stripped (no `ppid-…`/`ses-…` leak); board_os tests + live API green.

## Work Log
- 2026-06-01 [claude]: Status transitioned to complete via cos task-done.
