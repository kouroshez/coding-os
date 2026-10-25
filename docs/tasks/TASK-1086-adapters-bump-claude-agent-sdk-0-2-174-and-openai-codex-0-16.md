---
id: TASK-1086
title: "Adapters: bump claude-agent-sdk 0.2.174 and openai-codex 0.163; verbatim dispatch prompts; codex effort"
swimlane: adapters
kind: feature
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-10-25
started: 2026-10-25
completed: 2026-10-25
agent_session: ses-claude-20261025-014558-18d4
depends_on: []
blocked_by: []
references: []
---
# TASK-1086: Adapters: bump claude-agent-sdk 0.2.174 and openai-codex 0.163; verbatim dispatch prompts; codex effort

**Outcome (one sentence):** Both adapters run on the newest published SDKs, formula dispatch stops expanding `@path`/slash commands inside model-written input, and a codex role can carry a reasoning effort the SDK actually accepts.

## Read First
- docs/adapters/claude-sdk.md
- docs/engineering/dispatcher-contract.md
- src/adapters/codex/adapter.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** uv.lock resolves claude-agent-sdk 0.2.174 and openai-codex 0.163.0
- **When** the adapters matrix row runs (`uv run --extra codex-sdk pytest tests/test_adapters_*.py tests/test_adapter_parity.py tests/test_codex_chat_provider.py -q`) plus the dispatcher suites
- **Then** it passes; the Claude dispatcher passes `verbatim_prompts=True`; the Hub chat sets `snapshot` explicitly; codex declares only efforts read live from `client.models()` and forwards `request.effort` to `thread.run`

## Work Log
- 2026-10-25 [claude]: Locked claude-agent-sdk 0.2.174 (CLI 2.1.310) and openai-codex 0.163.0 (cap lifted to <0.164); global cos tool…
- 2026-10-25 [claude]: Status transitioned to complete via cos task-done.
