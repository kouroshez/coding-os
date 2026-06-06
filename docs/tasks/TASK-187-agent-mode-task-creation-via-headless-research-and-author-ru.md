---
id: TASK-187
title: "Agent-mode task creation via headless research-and-author runner"
swimlane: core
kind: feature
epic: agent-hub
labels: [ready]
status: complete
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
# TASK-187: Agent-mode task creation via headless research-and-author runner

**Outcome (one sentence):** From the create-task modal (agent mode), a prompt + model launches a headless Claude session restricted to cos_* tools (cos_graph_*/cos_doc_search/cos_task_create) with a research+author system prompt; it researches and writes one well-formed task, attributed to that executor session.

## Read First
- docs/engineering/agent-hub-orchestration.md
- src/core/web/routes/cognition.py
- src/adapters/claude/sdk_dispatcher.py
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the Claude SDK is available
- **When** the user submits a prompt (+ model) in the create modal's agent mode
- **Then** POST /api/cognition/author-task runs a fresh headless session whose allow-list is the cos MCP wildcard (no Write/Edit/Bash, so it cannot touch code), with a research+author system prompt; it SSE-streams and creates one task via cos_task_create; the board refreshes. Guard tests + make ui-build green. Honest Claude-only.

## Work Log
- 2026-06-06 [claude]: Added POST /api/cognition/author-task: a headless Claude session with allow-list 'mcp__coding-os__*' (+ Write/Edit/Bash 
