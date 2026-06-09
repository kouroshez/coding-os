---
id: TASK-284
title: "Purge phantom cos_retrieve router + reorder four-layer retrieval table + align docs"
swimlane: docs
kind: docs
epic: retrieval-routing-fix
labels: [routing, agent-confusion, ssot, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-09
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260609-143642-c7c5
depends_on: []
blocked_by: []
references: []
---
# TASK-284: Purge phantom cos_retrieve router + reorder four-layer retrieval table + align docs

**Outcome (one sentence):** Eliminate the documented-but-undefined cos_retrieve router (root cause of "ask about graph -> agent goes to memory"). Purge all 7 references (CLAUDE.md, AGENTS.md, src/core/rules/memory.md, src/core/rules/api-contract-discipline.md, src/core/skills/agent-memory/SKILL.md, src/core/skills/llm-patterns/SKILL.md) and repoint them to the four-layer decision table + nudge mechanism. Reorder the four-layer table so structural / code-conceptual queries route to GRAPH/CODE first and Agent Memory LAST. Resolve the dangling docs/engineering/retrieval-routing.md (create the contract pointing at the table+nudge, or remove every ref). Regen golden fixtures + adapter templates so consumer copies (tests/golden/**) carry no phantom ref.

## Read First
- AGENTS.md
- src/core/rules/memory.md
- src/core/skills/agent-memory/SKILL.md
- src/core/skills/llm-patterns/SKILL.md

## Work Log
- 2026-06-09 [claude]: Purged phantom cos_retrieve (9 refs across AGENTS.md, rules/memory.md, rules/api-contract-discipline.md, skills/agent-me
