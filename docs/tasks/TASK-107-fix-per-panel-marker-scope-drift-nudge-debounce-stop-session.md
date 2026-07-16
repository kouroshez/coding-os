---
id: TASK-107
title: "Fix per-panel marker-scope drift — nudge debounce, Stop session-id, capture-work-log, intent.json, task-mode"
swimlane: core
kind: bug
epic: hook-remediation
labels: [hooks, multi-agent, state, audit-n3, ready]
status: archive
priority: P1
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-107: Fix per-panel marker-scope drift — nudge debounce, Stop session-id, capture-work-log, intent.json, task-mode

**Outcome (one sentence):** Debounce markers written and cleared at the same scope (panel-dir); Stop hooks read a non-empty session-id via stdin upgrade + agent-dir fallback; capture-work-log reads panel-dir `.task-current`; `.intent.json` + nudge markers panel-scoped.

## Read First
- src/core/hooks/session-context.sh
- src/core/hooks/nudge-thinking-os.sh
- src/core/hooks/session-end.sh
- src/core/hooks/cos-env.sh

## Repro Steps
1. Open two Claude panels on the same project (same agent → same `$COS_AGENT_DIR`, distinct `$COS_PANEL_DIR`).
2. Panel A triggers nudge-thinking-os; marker written to `$COS_AGENT_DIR/.nudge-*` but session-context clears `$COS_PANEL_DIR/.nudge-*` → debounce never resets → nudge fires once per agent lifetime, silent in panel B.
3. On Claude Stop, session-end.sh / warn-abandoned-task.sh read session-id from a state file without stdin upgrade → empty → silent no-op.
Expected: markers scoped to panel-dir, cleared each SessionStart; Stop hooks resolve a non-empty session-id; capture-work-log reads panel `.task-current`.
Actual: agent-dir writes vs panel-dir clears; empty session-id on Stop; capture-work-log reads wrong dir.

## Acceptance (G/W/T)
- **Given** two panels of the same agent, **When** each triggers a nudge, **Then** each panel's debounce marker lives under its own `$COS_PANEL_DIR` and is cleared at that panel's SessionStart.
- **Given** a Claude Stop event, **When** session-end / warn-abandoned-task run, **Then** they resolve a non-empty session-id (stdin upgrade then agent-dir fallback) and act, not silently no-op.
- **Given** an active task in a panel, **When** capture-work-log runs, **Then** it reads `${COS_PANEL_DIR:-$COS_AGENT_DIR}/.task-current`.
- **Given** the per-panel allowlist, **When** `.intent.json` / `.*-nudged` markers are written, **Then** they route via `cos_state_path` to the panel dir.

## Work Log
- 2026-06-05 [claude]: Panel-scoped 6 marker classes (nudge debounce, .intent.json, .task-mode, .*-nudged, capture-work-log, warn-graph-empty) 
