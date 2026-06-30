---
id: TASK-654
title: "Relocate wordpress skill from core/skills to the template tree (stops over-shipping to all projects)"
swimlane: templates
kind: bug
epic: stack-completeness-v2
labels: [wordpress, skill, drift, wave-2, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-30
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-654: Relocate wordpress skill from core/skills to the template tree (stops over-shipping to all projects)

**Outcome (one sentence):** The wordpress skill lives under src/templates/wordpress/skills/wordpress/ so it ships only to wordpress projects, not universally via core/skills (the manifest currently lists .claude/skills/wordpress/SKILL.md across non-wordpress sections too).

## Read First
- src/core/skills/wordpress/SKILL.md
- src/templates/wordpress/stack.yaml
- src/cli/materialize_file.py

## Repro Steps
1. `grep -c '.claude/skills/wordpress/SKILL.md' src/core/scaffold_manifest.json` → present in many non-wordpress sections.
2. `ls src/core/skills/wordpress` exists, while every other stack ships its skill under src/templates/<stack>/skills/<stack>/.
Expected: wordpress skill ships only with the wordpress stack. Actual: it ships to every project as a core skill.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a non-wordpress scaffold (e.g. django), **When** generated, **Then** .claude/skills/ does NOT contain wordpress.
**Given** a wordpress scaffold, **When** generated, **Then** .claude/skills/wordpress/SKILL.md is present.
**Given** the relocation, **When** manifest-regen + golden recapture + test_template_scaffold + stack-lint(30) run, **Then** all green.

## Work Log
