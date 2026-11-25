---
id: TASK-1119
title: "fix(scaffold): consumer scaffold ships caches, cognition-only rules and broken links"
swimlane: templates
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-11-24
started: 2026-11-24
completed: 2026-11-24
agent_session: ses-claude-20261123-135444-89e7
depends_on: []
blocked_by: []
references: []
---
# TASK-1119: fix(scaffold): consumer scaffold ships caches, cognition-only rules and broken links

**Outcome (one sentence):** A fresh `cos init` project carries no cache directories, no rule for a module it did not enable, stack rules that scope by path, skill suggestions only from its own stacks, and no dead links in AGENTS.md or rules.

## Read First
- src/cli/_init_scaffold.py
- src/cli/_module_rules_cascade.py
- src/core/hooks/enforce-skill.sh
- docs/architecture/meta-project.md

## Repro Steps
Scaffold a new project with `cos init` (meta-free stack, cognition off) into a temp dir, then: `find . -name .ruff_cache -o -name __pycache__`; `ls .claude/rules/model-routing.md`; `head -5 .claude/rules/<stack>*.md` shows `globs:`; trigger enforce-skill on a file and read the suggestion list; run a link checker over AGENTS.md and .claude/rules.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a fresh scaffold, **When** it is listed, **Then** no .ruff_cache or __pycache__ exists inside it.
- **Given** cognition is off, **When** the scaffold is listed, **Then** model-routing.md is absent.
- **Given** a stack rule, **When** its frontmatter is read, **Then** it scopes with `paths:`.
- **Given** enforce-skill blocks, **When** it names skills, **Then** each belongs to an installed stack.
- **Given** AGENTS.md and the rules, **When** links are checked, **Then** none points to a missing file.

## Work Log
- 2026-11-24 [claude]: Plan: stack.yaml rule globs are the SSOT; rule files get a paths: frontmatter generated from them (Claude reads only…
- 2026-11-24 [claude]: Verified in a clean clone holding only this diff: golden parity + rules fresh 11, template scaffold 145 (+1 skip),…
- 2026-11-24 [claude]: commit b71c01135d — fix(scaffold): stop shipping caches, off-module rules, unscoped stack rules and dead links
- 2026-11-24 [claude]: Security auditor round 1: S1 (low) fixed in 88067d6e. A link target outside the project is no longer probed, and an…
- 2026-11-24 [claude]: Reviewer round 1 (8 findings), rework: enforce-skill now names clean-code, which every gate accepts (the old remedy…
- 2026-11-24 [claude]: Round 1 rework, all 11 findings. Items 1-8 are in c1aec4a7, which also fixes a regression the golden diff caught:…
- 2026-11-24 [claude]: Round 1 rework: all 11 findings fixed in c1aec4a7 + 8470003c, incl. a regression the golden diff caught (lexical link…
- 2026-11-24 [claude]: Status transitioned to complete via cos task-done.
