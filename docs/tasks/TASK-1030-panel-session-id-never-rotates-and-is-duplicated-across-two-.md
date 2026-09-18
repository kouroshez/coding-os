---
id: TASK-1030
title: "Panel session-id never rotates and is duplicated across two panels"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-31
started: null
completed: 2026-09-13
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-1030: Panel session-id never rotates and is duplicated across two panels

**Outcome (one sentence):** Every panel carries its own freshly minted session id, so two concurrent panels never share a `ses=` tail and no panel inherits an id from a conversation months old.

## Read First
- src/core/hooks/_cos_env_state.sh (`cos_panel_upgrade_from_payload`)
- src/core/hooks/session-context.sh (SessionStart:startup minting)
- src/core/rules/transparency-banner.md § Concurrency + per-field accuracy

## Repro Steps
1. `for d in .coding-os/claude/panels/*/; do printf '%s ' "$(basename $d)"; cat "$d/session-id"; done`
2. Observed 2026-09-13: panels `5ac9fe2e…` and `8ee96650…` both read
   `ses-claude-20260527-151803-0b9f` — one id, two live panels — while the two
   panels that did get a SessionStart:startup carry distinct ids stamped today.
3. Root cause: `cos_panel_upgrade_from_payload` seeded a missing panel
   `session-id` by mirroring `$COS_AGENT_DIR/session-id`, an agent-level file
   holding whichever panel wrote last and rotated by nothing. Its sibling
   `_session_pulse.sh` already refuses that file by name ("NEVER fall back to
   $COS_AGENT_DIR/session-id — that file is a fossil"); the guard was hardened
   in one reader and left open in the writer.
Expected: one id per panel, minted when the panel first appears.
Actual: every panel that starts without a startup event copies the same
fossil, so `ses=` collides in the banner and session-keyed state reaches back
to a conversation 3.5 months old.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a panel whose `session-id` file does not exist yet
**When** any hook sources `cos-env.sh`
**Then** the panel is seeded with a newly minted id, never a copy of
`$COS_AGENT_DIR/session-id`.

**Given** two panels seeded in the same second
**When** their ids are compared
**Then** they differ, because the id carries random suffix entropy.

**Given** the two writers that mint session ids
**When** either runs
**Then** both emit `ses-<agent>-YYYYMMDD-HHMMSS-xxxx` from one shared helper,
so a reader parsing the tail never meets a second shape.

## Work Log
- 2026-09-14 [claude]: Reproduced live: panels 5ac9fe2e and 8ee96650 both read ses-claude-20260527-151803-0b9f, an id minted 3.5 months…
- 2026-09-14 [claude]: Status transitioned to complete via cos task-done.
