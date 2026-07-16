---
id: TASK-246
title: "Onboarding: POST /cognition/onboard docs-scoped session"
swimlane: core
kind: feature
epic: hub-redesign
labels: [ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-20260608-024900-f2b0
depends_on: []
blocked_by: []
references: []
---
# TASK-246: Onboarding: POST /cognition/onboard docs-scoped session

**Outcome (one sentence):** Add POST /cognition/onboard running an onboarder session allowed to Write only under docs/.

## Read First
- src/core/web/routes/cognition.py — `chat_new` (streaming handler to model) + `author-task` (~line 899; allowed_tools/disallowed_tools at ~937-938 — the tool-scoped session pattern).
- docs/adapters/claude-sdk.md — ClaudeAgentOptions allowed_tools/disallowed_tools.

## Context / Approach
Mirror author-task but set `allowed_tools` to permit Write/Edit ONLY under docs/** (plus mcp__coding-os__*), disallowing writes elsewhere. Inject role=onboarder (TASK-245) via _role_system_prompt. A named endpoint keeps the docs-scoped permission set auditable. Depends on TASK-245.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an onboard session, **When** it attempts a Write outside docs/, **Then** the write is rejected.
- **Given** an onboard session, **When** it writes under docs/, **Then** the write succeeds.

## Work Log
- 2026-06-08 [claude]: Added POST /api/cognition/onboard: dontAsk + PreToolUse hook denies any Write/Edit outside docs/ (can_use_tool is skippe
