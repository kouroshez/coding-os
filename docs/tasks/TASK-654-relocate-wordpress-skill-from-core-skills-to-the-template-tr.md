---
id: TASK-654
title: "Relocate wordpress skill from core/skills to the template tree (stops over-shipping to all projects)"
swimlane: templates
kind: bug
epic: stack-completeness-v2
labels: [wordpress, skill, drift, wave-2, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-30
started: 2026-06-30
completed: 2026-06-30
agent_session: ses-claude-20260630-012042-78c9
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
- 2026-06-30 [claude]: Edit test_scan_wp_smells.py
- 2026-06-30 [claude]: wordpress skill->templates/wordpress/skills; manifest 56->4 sections; adapter+scan-test refs fixed; manifest+goldens…
