---
id: TASK-311
title: "Codex sdk_dispatcher drops DispatchRequest.model \u2014 forward --model to codex CLI per dispatcher contract"
swimlane: adapters
kind: bug
epic: null
labels: [ready, adapter-parity, audit-2026-06-09]
status: icebox
priority: P3
appetite: 1d
created: 2026-06-10
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-311: Codex sdk_dispatcher drops DispatchRequest.model — forward --model to codex CLI per dispatcher contract

**Outcome (one sentence):** `src/adapters/codex/sdk_dispatcher.py` forwards `request.model` to the codex subprocess invocation (`--model <id>`) when set, restoring dispatcher-contract parity instead of silently ignoring the field.

## Read First
- src/adapters/codex/sdk_dispatcher.py (~L85 — subprocess argv built without --model)
- docs/engineering/dispatcher-contract.md (parity rules: model is adapter-forwarded)
- src/core/thinking_os/dispatcher.py (DispatchRequest.model semantics)

## Repro Steps
1. Build a DispatchRequest with `model="gpt-5-codex"` and dispatch via the codex dispatcher.
2. Inspect the subprocess argv.
Expected: argv contains `--model gpt-5-codex`.
Actual: field is dropped; codex always runs its CLI-default model.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `DispatchRequest.model="gpt-5-codex"`
- **When** the codex dispatcher builds its subprocess command
- **Then** argv includes `--model gpt-5-codex`
- **Given** `model=None`
- **When** the command is built
- **Then** no `--model` flag is added; both covered by tests/test_adapters.py cases (no live codex binary needed — assert argv construction)

## Work Log
