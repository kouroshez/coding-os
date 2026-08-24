---
id: TASK-1023
title: "Skill references/ and assets/ never reach consumer projects \u2014 only SKILL.md is symlinked"
swimlane: cli
kind: bug
epic: null
labels: [skills, cli, governance]
status: "in_progress"
priority: P2
appetite: 1d
created: 2026-08-24
started: 2026-08-24
completed: null
agent_session: ses-claude-20260820-192937-ef87
depends_on: []
blocked_by: []
references: []
---

# TASK-1023: Skill references/ and assets/ never reach consumer projects — only SKILL.md is symlinked

**Outcome (one sentence):** A consumer project receives the whole skill, so a SKILL.md that links references/ or assets/ resolves instead of dangling.

## Read First
- src/cli/_skill_project.py
- src/core/skills/humanizer/SKILL.md
- tests/golden/claude_base/.claude/skills/

## Repro Steps
Run cos init for any preset, then list .claude/skills/clean-code/ or .claude/skills/humanizer/ in the scaffold: each contains SKILL.md alone. Confirmed in tests/golden/claude_base/.claude/skills/. Every relative link in those SKILL.md files to references/*.md is therefore broken in a consumer, including humanizer's pattern catalogue and its false-positive guardrails — the part that stops a review pass from over-flagging.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a skill directory containing `references/` or `assets/`
  **When** `cos init` renders a consumer project
  **Then** those subdirectories are present in the project's skills dir and every relative link in SKILL.md resolves.
- **Given** the fix changes what ships per project
  **When** it lands
  **Then** the context-budget figures in README are re-measured, since skills load on demand and must not enter the always-on total.

## Work Log
- 2026-08-24 [claude]: Edit _skill_project.py
- 2026-08-24 [claude]: Edit _skill_project.py
- 2026-08-24 [claude]: Edit install-adapter.sh
- 2026-08-24 [claude]: Edit link-stack-skills.sh
- 2026-08-24 [claude]: Edit SKILL.md
- 2026-08-24 [claude]: Edit install_commands.py
- 2026-08-24 [claude]: Edit install_commands.py
