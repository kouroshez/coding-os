---
id: TASK-084
title: "Codex SDK formula-dispatcher (openai-codex) — parallel to claude sdk_dispatcher for sub-agent spawning"
swimlane: infra
kind: feature
epic: null
labels: [codex, sdk, cognition, formula-dispatch]
status: icebox
priority: P2
appetite: "1d"
created: 2026-06-04
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-084: Codex SDK formula-dispatcher (openai-codex) — parallel to claude sdk_dispatcher for sub-agent spawning

**Outcome (one sentence):** cos_dispatch_formula_run can target Codex (Rule 16), not just Claude. Build src/adapters/codex/sdk_dispatcher.py mirroring src/adapters/claude/sdk_dispatcher.py using the openai-codex python SDK (0.1.0b2): Codex()/thread_start(model,approval_mode,sandbox)/thread.run() → TurnResult.items/final_response, with stream()+steer()+interrupt() for mid-turn control and Sandbox(read_only/workspace_write/full_access)+ApprovalMode for guardrails. Add `codex-sdk = ["openai-codex>=0.1.0b2"]` optional extra in pyproject (NOT core — 75MB cli-bin); fix codex adapter.yaml sdk_package `openai`→`openai_codex` so doctor reports the right version; add a doctor C-check for openai_codex import. Note: the SDK exposes NO pre-tool hook — enforcement during SDK-driven runs is via Sandbox + stream/interrupt (reactive), distinct from CLI-hook enforcement (TASK-083). Unit-test with a mocked Codex client (real dispatch needs OPENAI auth → nightly/sdk_e2e marker only, like claude).

## Read First
- src/adapters/claude/sdk_dispatcher.py
- docs/adapters/claude-sdk.md
- https://github.com/openai/codex/blob/main/sdk/python/docs/api-reference.md
- src/adapters/codex/adapter.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
