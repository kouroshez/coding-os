---
id: TASK-667
title: "Live dispatch observability \u2014 tee role-dispatch to an append-only run-event sink the Hub tails + replays; fix dead sdk_uuid modal link"
swimlane: core
kind: feature
epic: live-observability
labels: [hub, dispatch, sse, observability, ready]
status: complete
priority: P1
appetite: 2d
created: 2026-06-30
started: 2026-06-30
completed: 2026-06-30
agent_session: ses-claude-20260630-221108-17bf
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
- 2026-07-01 [claude]: Edit sdk_dispatcher.py
- 2026-07-01 [claude]: Edit sdk_dispatcher.py
- 2026-07-01 [claude]: Edit sdk_dispatcher.py
- 2026-07-01 [claude]: Edit sdk_dispatcher.py
- 2026-07-01 [claude]: Edit test_dispatch_trace.py
- 2026-07-01 [claude]: Edit cognition.py
- 2026-07-01 [claude]: Edit cognition.py
- 2026-07-01 [claude]: Edit cognition.py
- 2026-07-01 [claude]: Edit cognition.py
- 2026-07-01 [claude]: Edit test_cognition_dispatch_obs.py
- 2026-07-01 [claude]: Edit cognition.py
- 2026-07-01 [claude]: Edit cognition.py
- 2026-07-01 [claude]: Edit test_cognition_dispatch_obs.py
- 2026-07-01 [claude]: Edit test_cognition_dispatch_obs.py
- 2026-07-01 [claude]: Edit test_cognition_dispatch_obs.py
- 2026-07-01 [claude]: Edit TraceTimeline.tsx
- 2026-07-01 [claude]: Edit TraceTimeline.tsx
- 2026-07-01 [claude]: Edit hub-architecture.md
- 2026-07-01 [claude]: Tee dispatch turns to cognition trace sink (content off by default, fail-open); /api/cognition/trace/{id}/stream SSE…
- 2026-07-01 [claude]: committed 82f308fd · 8 files
- 2026-07-01 [claude]: Status transitioned to complete via cos task-done.
- 2026-07-01 [claude]: committed d82ffdcc · 20 files
