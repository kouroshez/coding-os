---
id: TASK-986
title: "tool_guard must not fail open when the runtime SDK is absent"
swimlane: adapters
kind: bug
epic: honest-benchmarks
labels: [ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-08-15
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-986: tool_guard must not fail open when the runtime SDK is absent

**Outcome (one sentence):** An adapter that cannot carry the kernel's pre-tool-use policy says so loudly instead of returning None, so a write-scoping guard can never be silently dropped from an unattended session.

## Read First
- src/adapters/claude/chat_provider.py
- src/core/web/routes/cognition_onboarding.py
- tests/test_chat_port.py

## Repro Steps
src/adapters/claude/chat_provider.py tool_guard() returns None when the SDK import fails. Core passes that result straight into hooks={"PreToolUse": [...]} in cognition_onboarding.py for a session running permission_mode="dontAsk", where _deny_non_docs_write is the only control scoping writes to docs/. A None entry removes the policy with no error. Latent today because _chat_runtime() gates on the same probe, but the port gives a second adapter no way to signal it cannot carry the guard.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** an adapter whose runtime cannot build a pre-tool-use matcher, **When** core asks it to carry a guard, **Then** it raises rather than returning a value core will silently drop.
- **Given** the onboarding session builder, **When** the guard cannot be constructed, **Then** the session is not started unguarded.
- **Given** a regression test, **When** it simulates the absent runtime, **Then** it fails against the current code and passes after the fix.

## Work Log
