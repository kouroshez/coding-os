---
id: TASK-667
title: "Live dispatch observability \u2014 tee role-dispatch to an append-only run-event sink the Hub tails + replays; fix dead sdk_uuid modal link"
swimlane: core
kind: feature
epic: live-observability
labels: [hub, dispatch, sse, observability, ready]
status: icebox
priority: P1
appetite: 2d
created: 2026-06-30
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-667: Live dispatch observability — tee role-dispatch to an append-only run-event sink the Hub tails + replays; fix dead sdk_uuid modal link

**Outcome (one sentence):** Role-dispatch runs (sdk_dispatcher) tee their stream to an append-only run-event jsonl sink that a Hub web route tails live over SSE and can replay, so every dispatched agent session is trackable and viewable in the web panel in real time, and the dead sdk_uuid modal link resolves to the persisted transcript — with the returned EvidenceBundle untouched.

## Read First
- src/adapters/claude/sdk_dispatcher.py
- src/core/web/routes/hooks.py
- docs/engineering/hub-architecture.md
- docs/adapters/claude-sdk.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a role-dispatch run, **When** it executes, **Then** each turn is appended to an append-only run-event sink with partial-message content off by default, without altering the returned EvidenceBundle.
- **Given** the Hub open during a dispatch, **When** the run streams, **Then** a web route tails the sink over SSE and renders the live session, reusing the stream_hooks/_drain_log pattern.
- **Given** a completed dispatch, **When** a user opens its row, **Then** the sdk_uuid links to the persisted transcript with no dead modal.

## Work Log
