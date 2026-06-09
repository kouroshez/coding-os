---
id: TASK-288
title: "Session-validate panel-dir fallbacks + loud ppid-collision detector across hooks"
swimlane: core
kind: bug
epic: panel-state-isolation
labels: [state-isolation, hooks, concurrency, fail-closed, ready]
status: complete
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
# TASK-288: Session-validate panel-dir fallbacks + loud ppid-collision detector across hooks

**Outcome (one sentence):** The ${COS_PANEL_DIR:-$COS_AGENT_DIR} fallback can read a sibling panel's fossil during the startup window; and when no runtime session-id var is exported, _cos_resolve_panel_id falls to a ppid-<hash> that can collide between two panels sharing a PPID — silently sharing one state dir. Add a one-time LOUD warning + diagnostic marker whenever the ppid-* fallback path is taken (converts a silent collision into an observed, fail-safe event). Ensure every panel-first fallback reader validates session-id and rejects sibling fossils (audit enforce-task-start, track-skill, enforce-skill, enforce-doc-anchor, agent-presence, reclaim-sweep, session-context role readers). No silent cross-panel reads.

## Read First
- src/core/hooks/cos-env.sh
- src/core/hooks/check-state.sh
- docs/engineering/state-files.md

## Repro Steps
1. Unset `CLAUDE_CODE_SESSION_ID` and all adapter session vars (CLAUDE_SESSION_ID, CURSOR_*, CODEX_SESSION_ID).
2. Source `cos-env.sh` in two shells that share the same PPID.
3. Both resolve an identical `ppid-<hash>` panel id → identical `COS_PANEL_DIR` → `.task-current` / `.thinking_os-gate` / `.active-skill` overwrite each other.
Expected: a one-time loud warning + diagnostic marker that the ppid fallback (no runtime session id) is active and panels may collide.
Actual: a silently shared panel dir; cross-panel cognitive-state clobber with no signal.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** no runtime session-id var is exported (the `ppid-<hash>` fallback path in _cos_resolve_panel_id).
- **When** the resolver falls through to ppid, and panel-first state readers encounter a sibling fossil in the agent dir.
- **Then** a one-time loud warning + diagnostic marker is emitted on the ppid path (collision becomes observed, never silent), every panel-first fallback reader validates session-id and rejects sibling fossils, `test_cos_env_panel_resolution.py` asserts the warning, and `make verify-hooks` is green.

## Work Log
- 2026-06-09 [claude]: Added ppid-collision detector: cos-env.sh classifies COS_PANEL_ID_SOURCE (ppid|session) cheaply from the id prefix; sess
