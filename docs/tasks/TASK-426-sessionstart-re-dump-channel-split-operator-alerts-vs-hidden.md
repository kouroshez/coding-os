---
id: TASK-426
title: "SessionStart re-dump: channel-split operator alerts vs hidden agent context"
swimlane: core
kind: bug
epic: null
labels: [governance, docs-update, hooks, sessionstart, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-15
started: 2026-06-15
completed: 2026-06-15
agent_session: ses-claude-20260615-012959-d18c
depends_on: []
blocked_by: []
references: []
---
# TASK-426: SessionStart re-dump: channel-split operator alerts vs hidden agent context

**Outcome (one sentence):** SessionStart stops printing the agent digest / recovery / MCP-prime block into the chat (and re-dumping it mid-chat on every auto-compact). Operator-facing alerts (uncommitted-work, active-tasks) stay visible on the operator channel; agent-only context moves to a single hidden additionalContext envelope; the heavy digest is suppressed on the same-session compact source.

## Read First
- src/core/hooks/session-context.sh
- src/core/rules/transparency-banner.md
- docs/engineering/state-files.md
- src/adapters/codex/hooks/codex-sessionstart-dispatch.sh
- src/core/hooks/_helpers/extract_additional_context.py

## Repro Steps
Drive a long Claude Code session to the context ceiling (~430k). The runtime auto-compacts, firing SessionStart source=compact; session-context.sh's bare printf/echo SessionStart blocks (recovery rules + [Session State] + [Agent Digest] + digest.md + trajectory/routing/token-econ) print to stdout, which Claude surfaces as operator-visible 'SessionStart:compact hook success: ...' lines mid-chat AND injects to context — a multi-thousand-token wall in the middle of the conversation.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a Claude SessionStart source=compact, **When** session-context.sh runs, **Then** stdout is exactly one additionalContext JSON envelope (no operator-visible digest/recovery wall) and the digest/trajectory/routing block is skipped.
- **Given** a Claude SessionStart source=startup, **When** it runs, **Then** [Uncommitted Work] + [Session Start] active-tasks go to stderr (operator-visible) while [Agent Digest]/[MCP Prime]/[Session State]/recovery-rules go into the hidden envelope.
- **Given** a Codex SessionStart delegate, **When** codex-sessionstart-dispatch.sh captures it 2>&1, **Then** session-context.sh emits plain text (no JSON envelope) so extract_additional_context.py's single json.loads never receives literal JSON.
- **Given** the change is complete, **When** `make verify-hooks` runs, **Then** it passes; and a synthetic SessionStart pipe per source asserts the channel split.

## Work Log
- 2026-06-15 [claude]: Edit transparency-banner.md
- 2026-06-15 [claude]: Edit state-files.md
- 2026-06-15 [claude]: Edit session-context.sh
- 2026-06-15 [claude]: Edit session-context.sh
- 2026-06-15 [claude]: Edit session-context.sh
- 2026-06-15 [claude]: Edit session-context.sh
- 2026-06-15 [claude]: Edit verify_ss.py
- 2026-06-15 [claude]: Implemented channel split in session-context.sh: SS_VISIBLE (uncommitted-work, active-tasks) -> stderr; SS_HIDDEN (recov
- 2026-06-15 [claude]: committed cae258bc: docs/engineering/state-files.md, src/core/hooks/session-context.sh, src/core/rules/transparency-bann
