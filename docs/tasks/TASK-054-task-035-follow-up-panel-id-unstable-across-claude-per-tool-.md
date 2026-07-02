---
id: TASK-054
title: "TASK-035 follow-up: panel-id unstable across Claude per-tool-call hook subprocesses (ppid scatter) + claude/claude double-nest"
swimlane: core
kind: bug
epic: null
labels: []
status: archive
priority: P1
appetite: "1d"
created: 2026-06-01
started: 2026-06-01
completed: 2026-06-01
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: ["TASK-035", "TASK-051", "TASK-052"]
---
# TASK-054: TASK-035 follow-up: panel-id unstable across Claude per-tool-call hook subprocesses (ppid scatter) + claude/claude double-nest

**Outcome (one sentence):** One Claude session resolves ONE stable `$COS_PANEL_DIR` across every hook invocation, so cognitive-state markers (.task-current/.thinking_os-gate/.active-skill/.doc-anchor/session-id) stop scattering across dozens of ephemeral `ppid-*` panels and the agent-level/`claude/claude` fossils disappear.

## Read First
- src/core/hooks/cos-env.sh — `_cos_resolve_panel_id` (priority #4 ppid fallback) + `COS_STATE_DIR`/`COS_AGENT_DIR` (line 30/105)
- src/core/hooks/session-context.sh — sole caller of `cos_panel_upgrade_from_payload`
- docs/engineering/state-files.md — TASK-035 per-panel contract (the spec to amend)

## Repro Steps
1. Run an interactive Claude session; fire several tool calls.
2. `find .coding-os/claude/panels -name '.thinking_os-gate' -o -name '.task-current'` → markers for ONE session land in DIFFERENT `ppid-*` panels.
3. `_cos_resolve_panel_id` falls to `ppid-<hash(PPID,agent)>`; Claude spawns each hook in a fresh subprocess so PPID (hence the hash) differs per tool call.

Expected: stable panel id per session → coherent state; `enforce-doc-anchor`/`thinking_os-gate`/`enforce-skill` see the markers the prompt hook wrote.
Actual: panel id ephemeral-per-call → state scatters; PreToolUse gates block on markers written to a sibling panel; HUD/banner read fossils. Also a stale `.coding-os/claude/claude/` double-nest exists where some context resolved `COS_STATE_DIR=.coding-os/claude` → `COS_AGENT_DIR=.coding-os/claude/claude`.

## Candidate fixes (decide in design)
- **A (preferred):** Claude adapter exports `CLAUDE_SESSION_ID` into the hook env → `_cos_resolve_panel_id` priority #3 resolves one stable id for ALL hooks (no stdin needed). Verify Claude Code passes it; else
- **B:** every stdin-reading hook calls `cos_panel_upgrade_from_payload` (not just session-context.sh) so all converge on the stdin `session_id` UUID panel.
- **C:** derive panel id from the agent-level `session-id` content hash (stable per session) — but revisit concurrent-session isolation (two sessions share agent-level session-id).
- Plus: root-cause + remove the `claude/claude` double-nest; GC orphan `ppid-*` panels.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** one interactive Claude session firing N tool calls,
- **When** the hooks run,
- **Then** all writes land in exactly one `$COS_PANEL_DIR`; PreToolUse gates never block on a sibling-panel marker; no new `claude/claude` nesting; banner + HUD read live (not fossil) state; full hook + state-file test sweep green.

## Work Log
- 2026-06-01 [claude]: Status transitioned to complete via cos task-done.
