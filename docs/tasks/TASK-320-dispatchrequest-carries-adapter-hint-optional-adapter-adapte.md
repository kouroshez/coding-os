---
id: TASK-320
title: "DispatchRequest carries adapter hint \u2014 optional adapter/adapter_budget_usd fields, factory mismatch warning"
swimlane: "thinking_os"
kind: feature
epic: null
labels: [delegation, audit-2026-06-09, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-10
started: 2026-06-09
completed: 2026-06-10
agent_session: ses-claude-20260527-151803-0b9f
depends_on: [TASK-308]
blocked_by: []
references: []
---
# TASK-320: DispatchRequest carries adapter hint — optional adapter/adapter_budget_usd fields, factory mismatch warning

**Outcome (one sentence):** DispatchRequest gains optional `adapter` + `adapter_budget_usd` fields (backward-compatible, None default) so supervisor decisions can name a target runtime; `get_dispatcher` logs a clear mismatch warning when request.adapter differs from the session adapter — the single-adapter-per-session constraint stays, the data pathway opens.

## Read First
- src/core/thinking_os/dispatcher.py (DispatchRequest dataclass + get_dispatcher factory)
- docs/engineering/dispatcher-contract.md (update spec FIRST — Rule 19)
- src/adapters/claude/sdk_dispatcher.py · src/adapters/codex/sdk_dispatcher.py (consumers must ignore unknown fields gracefully)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** existing callers constructing DispatchRequest without the new fields
- **When** thinking_os tests run
- **Then** all pass unchanged (fields optional, default None)
- **Given** request.adapter="codex" in a claude session
- **When** get_dispatcher resolves
- **Then** a warning names both adapters and dispatch proceeds on the session adapter
- **Given** dispatcher-contract.md
- **When** the diff lands
- **Then** the doc section for the new fields precedes the code change in the commit history

## Work Log
- 2026-06-10 [claude]: Shipped (score 9/10): DispatchRequest gains optional adapter + adapter_budget_usd (None defaults, backward-compatible);
- 2026-06-10 [claude]: committed f97bbe50: docs/engineering/dispatcher-contract.md, src/core/thinking_os/dispatcher.py, src/core/thinking_os/te
- 2026-06-10 [claude]: Status transitioned to complete via cos task-done.
