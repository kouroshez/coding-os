---
id: TASK-171
title: "Multi-script token estimation so truncated flag stops undercounting non-Latin payloads"
swimlane: core
kind: bug
epic: agent-economy
labels: [ready]
status: archive
priority: P1
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-171: Multi-script token estimation so truncated flag stops undercounting non-Latin payloads

**Outcome (one sentence):** The MCP envelope token budget and the standalone estimator use a script-aware conservative token estimate so meta.truncated and tokens_estimated stay honest for non-Latin (CJK/Arabic/Cyrillic) payloads, with ASCII behaviour unchanged.

## Read First

- docs/engineering/agent-economy-and-identity-roadmap.md (B1)
- docs/engineering/mcp-error-envelope.md
- src/core/thinking_os/tools/_shared.py

## Repro Steps

1. Build a dict whose serialized JSON is ~24 KB of CJK/Persian text (under the 32 KB char budget but well over the intended 8 K-token cap).
2. Pass it through ok(data).
3. meta.truncated stays False and meta.tokens_estimated is roughly chars/4 — a 2-3x undercount; the oversized payload is never trimmed and the coverage signal the graph-first contract trusts is wrong.

## Acceptance

- **Given** an envelope body whose serialized form is mostly non-Latin and exceeds the intended token budget,
- **When** it is wrapped by ok(),
- **Then** meta.truncated is True and meta.tokens_estimated reflects a conservative script-aware count, while an equivalently-sized ASCII payload trims at the same point as before (no regression).

## Work Log
- 2026-06-05 [claude]: Status transitioned to complete via cos task-done.
