---
id: TASK-1075
title: "Make .agents/memory the one file-based memory for every agent, as in Dana"
swimlane: infra
kind: feature
epic: null
labels: [ready, governance, docs-update]
status: in_progress
priority: P1
appetite: 1d
created: 2026-10-24
started: 2026-10-24
completed: null
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1075: Make .agents/memory the one file-based memory for every agent, as in Dana

**Outcome (one sentence):** Every coding-os project keeps durable memory as committed markdown in .agents/memory/ (one fact per file, MEMORY.md index plus one-level index-*.md sub-indexes); Claude reads it through its per-machine memory-dir symlink, Codex gets the index once per session from a hook, and a structural lint keeps the index inside what Claude loads.

## Read First
- src/core/rules/memory.md
- src/adapters/claude/hooks/ensure-agent-memory-link.sh
- /Users/ciro/Files/Project/Dana/src/Dana/scripts/docs/memory-drift.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a fresh cos init project cloned on another machine, **When** a Claude session starts, **Then** ~/.claude/projects/<slug>/memory is a symlink to the repo's .agents/memory.
- **Given** a Codex session, **When** the first prompt is submitted, **Then** MEMORY.md arrives as additional context once and not on later prompts.
- **Given** a memory file no index links, or a MEMORY.md over 200 lines or 25 KB, **When** make memory-lint runs, **Then** it fails naming the problem.
- **Given** coding-os's own .agents/memory, **When** make memory-lint runs, **Then** it passes and the DB-generated block is gone from MEMORY.md.

## Work Log
- 2026-10-25 [claude]: Plan (COMPLICATED): port Dana's model, not a new design — prime-memory-codex as a codex-scoped UserPromptSubmit…
- 2026-10-25 [claude]: Committed 4cacdb61. Verified in a clean clone one step at a time: templates/manifest/golden regen, verify-hooks,…
