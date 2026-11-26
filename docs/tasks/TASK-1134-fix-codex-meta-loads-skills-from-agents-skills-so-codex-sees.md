---
id: TASK-1134
title: "fix(codex): META loads skills from .agents/skills so Codex sees them; drop stale .codex/skills and commands"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-11-26
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1134: fix(codex): META loads skills from .agents/skills so Codex sees them; drop stale .codex/skills and commands

**Outcome (one sentence):** Codex in coding-os lists every shipped skill; findings C1 and C5 of docs/engineering/harness-loading-audit-2026-11.md are closed.

## Read First
- docs/engineering/harness-loading-audit-2026-11.md

## Repro Steps
In coding-os run `codex debug prompt-input --disable hooks -c 'mcp_servers={}'`: zero coding-os skills are listed because each .codex/skills/*/SKILL.md is a file symlink, which Codex 0.171 skips (audit C1).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the coding-os checkout after install, **When** `codex debug prompt-input` runs there, **Then** every skill under src/core/skills and src/templates/meta/skills is listed.
- **Given** META after the fix, **When** .codex is listed, **Then** it has no skills/ or commands/ dir.

## Work Log
