---
id: TASK-193
title: "Humanize traces with a readable summary and raw events behind a dev toggle"
swimlane: core
kind: feature
epic: agent-hub
labels: [ready]
status: archive
priority: P2
appetite: "1d"
created: 2026-06-06
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260605-183120-db30
depends_on: []
blocked_by: []
references: []
---
# TASK-193: Humanize traces with a readable summary and raw events behind a dev toggle

**Outcome (one sentence):** The Traces view defaults to a plain-language "what the agent did" summary (human labels for cognition event kinds, showing ts/label/role/phase) and hides the raw jsonl events behind a developer toggle.

## Read First
- docs/engineering/agent-hub-orchestration.md
- src/core/web/ui/src/features/cognition/TraceTimeline.tsx
- src/core/thinking_os/tracing.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a session's cognition trace
- **When** a non-developer opens the Traces view
- **Then** it shows a readable step list (human label per event kind + role/phase, not raw JSON); a "raw events" developer toggle reveals the original jsonl dump; make ui-build green.

## Work Log
- 2026-06-06 [claude]: TraceTimeline now defaults to a readable summary: humanLabel maps each cognition kind to plain language, humanDetail sho
