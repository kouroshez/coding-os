---
id: TASK-252
title: "Attention model: tab/favicon badge + Notification API"
swimlane: core
kind: feature
epic: hub-redesign
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-252: Attention model: tab/favicon badge + Notification API

**Outcome (one sentence):** Notify the human when an agent finishes or is blocked without staring at the tab.

## Read First
- src/core/web/ui/src/lib/use-event-stream.ts — the SSE hook to subscribe (live/reconnecting/closed).
- src/core/web/routes/stream.py — the agent-activity / presence-updated events emitted.
- src/core/web/ui/src/layout/AppShell.tsx — where a global badge/indicator mounts.

## Context / Approach
Subscribe (useEventStream) to agent-completed / agent-blocked / needs-input events; fire a tab-title badge "(1) Hub" + favicon dot + the Notification API, plus an in-app activity feed. This is near the product thesis — observing an AUTONOMOUS agent that runs long and stalls on blocking hooks; the human cannot be required to stare at the tab.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an agent-completed/blocked SSE event, **When** the tab is unfocused, **Then** a tab-title/favicon badge + a Notification fire.
- **Given** the tab is refocused, **When** viewed, **Then** the badge clears.

## Work Log
- 2026-06-08 [claude]: Added AttentionBell in AppShell: subscribes to dispatch-completed/agent-blocked/needs-input, raises tab-title+favicon ba
