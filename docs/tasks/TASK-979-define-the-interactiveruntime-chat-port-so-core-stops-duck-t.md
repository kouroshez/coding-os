---
id: TASK-979
title: "Define the InteractiveRuntime chat port so core stops duck-typing an SDK module"
swimlane: core
kind: refactor
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-14
started: 2026-08-14
completed: 2026-08-14
agent_session: ses-claude-20260814-120316-413b
depends_on: []
blocked_by: []
references: []
---
# TASK-979: Define the InteractiveRuntime chat port so core stops duck-typing an SDK module

**Outcome (one sentence):** Hub chat reaches a runtime through a named, adapter-implemented port, so a second in-process runtime drops in by implementing four functions instead of by happening to expose the Claude SDK's own attribute names.

## Read First
- docs/engineering/adapter-parity.md § Hub chat
- src/core/web/routes/_cognition_chat_sdk.py
- src/adapters/codex/chat_provider.py (the existing provider shape)

## Repro Steps
`_claude_sdk()` resolves a module from the adapter registry, but every caller
then uses the SDK's own surface — `sdk.list_sessions`, `sdk.get_session_info`,
`sdk.get_session_messages`, `sdk.query`. The kernel no longer spells
`claude_agent_sdk`, yet a new runtime must still expose those four names with
those exact signatures, so the coupling moved rather than left.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an adapter declaring the `chat` capability, **When** the Hub lists sessions, reads one, reads its messages or streams a turn, **Then** every call goes through that entrypoint, not through an SDK module attribute.
- **Given** `src/core/web/routes/**`, **When** grepped, **Then** no `sdk.<name>` call on a resolved runtime module remains.
- **Given** an adapter with no `chat` entrypoint, **When** the Hub chat routes are hit, **Then** they return the existing unavailable envelope rather than raising.
- **Given** the live Claude SDK, **When** the port is exercised, **Then** sessions/messages come back exactly as before — verified by running it, not by reading it.

## Work Log
- 2026-08-14 [claude]: Edit chat_provider.py
- 2026-08-14 [claude]: Edit _cognition_chat_sdk.py
- 2026-08-14 [claude]: Edit chat_provider.py
- 2026-08-14 [claude]: Edit cognition_onboarding.py
- 2026-08-14 [claude]: Edit _cognition_chat_sdk.py
- 2026-08-14 [claude]: Edit adapter-parity.md
- 2026-08-14 [claude]: Edit msg15.txt
- 2026-08-14 [claude]: commit 6dc3fc1843 — feat(adapters): give Hub chat a real port instead of a duck-typed SDK module
- 2026-08-14 [claude]: Done in 6dc3fc18. Adapters declare a `chat` capability and implement five functions; core resolves by capability and…
- 2026-08-14 [claude]: Status transitioned to complete via cos task-done.
