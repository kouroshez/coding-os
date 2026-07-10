---
id: TASK-806
title: "Restore P8 in Hub routes: move claude_agent_sdk imports out of src/core/web behind the dispatcher seam"
swimlane: core
kind: refactor
epic: null
labels: [review-sweep, architecture]
status: icebox
priority: P2
appetite: 1d
created: 2026-07-10
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-806: Restore P8 in Hub routes: move claude_agent_sdk imports out of src/core/web behind the dispatcher seam

**Outcome (one sentence):** src/core/web/routes/{cognition,presence,roles}.py no longer import claude_agent_sdk directly; Claude-specific session/chat capabilities reach the Hub through the adapter dispatcher seam (file-loaded sdk_dispatcher / capability probe), restoring the P8 guarantee that src/core never imports an adapter SDK — or, if the exception is deliberate, P8 is amended in AGENTS.md/constitution with the documented carve-out.

## Read First
- docs/architecture/meta-project.md
- docs/adapters/claude-sdk.md
- src/core/thinking_os/dispatcher.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
