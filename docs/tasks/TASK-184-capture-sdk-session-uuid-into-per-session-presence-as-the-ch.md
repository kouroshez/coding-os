---
id: TASK-184
title: "Capture SDK session uuid into per-session presence as the chat bridge"
swimlane: core
kind: feature
epic: agent-hub
labels: [ready]
status: archive
priority: P1
appetite: "4h"
created: 2026-06-06
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260605-183120-db30
depends_on: []
blocked_by: []
references: []
---
# TASK-184: Capture SDK session uuid into per-session presence as the chat bridge

**Outcome (one sentence):** The per-session presence record (sessions/&lt;coding-os-id&gt;.json) carries the host SDK session uuid (from the hook payload's `.session_id`) as `sdk_uuid`, so a task's agent_session can later resolve to its live chat transcript.

## Read First
- docs/engineering/agent-hub-orchestration.md
- src/core/hooks/agent-presence.sh
- src/core/hooks/_helpers/presence_write.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a hook payload carrying `.session_id` (the SDK uuid)
- **When** agent-presence.sh records presence
- **Then** the presence JSON gains an `sdk_uuid` field (preserved across events like `model`), backward-compatible with the 7/8-arg helper signature; a unit test covers the capture; bash -n + shellcheck + presence tests green. Design doc §1 updated to the per-session-mapping bridge (no tasks migration).

## Work Log
- 2026-06-06 [claude]: presence_write.py gains an optional sdk_uuid (8th arg, preserved across events); agent-presence.sh extracts the host .se
