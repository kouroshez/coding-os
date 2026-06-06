---
id: TASK-179
title: "Suppress fresh-panel banner when session-id is unresolved instead of rendering all-blank"
swimlane: core
kind: bug
epic: agent-economy
labels: [ready]
status: complete
priority: P3
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-179: Suppress fresh-panel banner when session-id is unresolved instead of rendering all-blank

**Outcome (one sentence):** When SES_TAIL is empty (panel session-id not yet seeded), session-context.sh suppresses USER_BANNER instead of emitting a misleading all-blank 'ses=? task=none gate=unset' line, so the agent skips the banner per the transparency-banner contract.

## Read First

- docs/engineering/agent-economy-and-identity-roadmap.md (B7)
- src/core/hooks/session-context.sh (banner build ~L601-619)
- src/core/rules/transparency-banner.md (skip-when-absent contract)

## Repro Steps

1. On a brand-new panel turn-1 where session-id cannot be resolved (COS_PANEL_ID empty), SES_TAIL is empty and _read_state rejects all state files.
2. session-context.sh renders the formal banner as 'ses=? mode=formal task=none gate=unset skill=- roles=- audit=-' — indistinguishable from a hung/broken agent, the worst possible first impression.

## Acceptance

- **Given** session-context.sh on a UserPromptSubmit where SES_TAIL is empty,
- **When** it builds USER_BANNER,
- **Then** USER_BANNER is empty (banner suppressed, agent skips per the rule), while a resolved session renders the normal banner unchanged; make verify-hooks passes.

## Work Log
- 2026-06-06 [claude]: Status transitioned to complete via cos task-done.
