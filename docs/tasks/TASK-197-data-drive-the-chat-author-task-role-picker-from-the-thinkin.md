---
id: TASK-197
title: "Data-drive the chat/author-task role picker from the thinking_os/agents producer (drop hardcoded role list)"
swimlane: core
kind: refactor
epic: agent-hub
labels: [ready]
status: archive
priority: P2
appetite: "1d"
created: 2026-06-06
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260605-183120-db30
depends_on: []
blocked_by: []
references: []
---
# TASK-197: Data-drive the chat/author-task role picker from the thinking_os/agents producer (drop hardcoded role list)

**Outcome (one sentence):** A `GET /api/cognition/roles` endpoint lists the real semantic roles from `src/core/thinking_os/agents/*.md` (the same producer `_role_system_prompt` loads from), and the chat role picker (NewChatForm) consumes it instead of a hardcoded list that can silently drift when a role is added or removed. (AgentTaskModal is model-only — no role picker — so it is unaffected.)

## Read First
- docs/engineering/agent-hub-orchestration.md (§9 Phase 4 / T18)
- src/core/web/routes/cognition.py (`_role_system_prompt`, route/envelope pattern)
- src/core/web/ui/src/features/cognition/NewChatForm.tsx (was hardcoded ROLES)
- src/core/rules/api-contract-discipline.md (producer is source of truth)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the role producer dir `src/core/thinking_os/agents/*.md`
- **When** the new-chat role picker renders
- **Then** its options come from `GET /api/cognition/roles` (filtered `^[a-z_]+$`, no leading-underscore helpers) via a `useRoles()` hook, the component carries no hardcoded authoritative role list, a fixture-backed test asserts the endpoint returns the known roles and excludes README/_helpers, and `tsc` + `make ui-build` + the route test are green.

## Work Log
- 2026-06-06 [claude]: Added GET /api/cognition/roles (helper _role_names lists thinking_os/agents/*.md, filter ^[a-z_]+$ minus _-prefixed); Ne
