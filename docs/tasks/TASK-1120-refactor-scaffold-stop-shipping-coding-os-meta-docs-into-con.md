---
id: TASK-1120
title: "refactor(scaffold): stop shipping coding-os meta docs into consumer projects"
swimlane: templates
kind: refactor
epic: null
labels: [ready, governance, docs-update]
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
# TASK-1120: refactor(scaffold): stop shipping coding-os meta docs into consumer projects

**Outcome (one sentence):** A consumer project receives only docs it needs to run coding-os; the meta-repo's own governance docs stay in coding-os and are linked, not copied.

## Read First
- src/cli/_init_scaffold.py
- src/core/scaffold_manifest.json
- docs/architecture/meta-project.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a fresh scaffold, **When** docs/ is listed, **Then** critical-rules.md, mcp-tool-inventory.md, wrapper-derivation.md, anatomy-contract.md and thinking_os-final-edition.md are absent. (Amended 2026-11-24: research-validation.md stays. It is a generic research playbook, the base domain-config's `default_playbook`, and linked by the django stack, not coding-os's own governance.)
- **Given** the shipped rules and skills, **When** their links are checked, **Then** none points at a removed doc.
- **Given** the same scaffold before and after, **When** always-loaded tokens are measured, **Then** the after figure is lower and both are reported.

## Work Log
- 2026-11-24 [claude]: commit 88067d6ec3 — fix(scaffold): never probe a copied page's link outside the project
- 2026-11-24 [claude]: commit 86f7b245a7 — refactor(scaffold): stop shipping coding-os's own governance docs into projects
- 2026-11-24 [claude]: commit 75b1680300 — fix(scaffold): shipped rules say where the removed governance docs live
- 2026-11-24 [claude]: commit 76acf754c7 — docs(playbooks): refresh the index entry for template-authoring
- 2026-11-24 [claude]: Token measurement on the same fastapi scaffold (cognition and cicd off, chars/4): before is the pre-change scaffold,…
- 2026-11-24 [claude]: Token measurement on the same fastapi scaffold (cognition and cicd off, chars/4): before is the pre-change scaffold,…
- 2026-11-24 [claude]: commit 78d972b5f1 — fix(scaffold): last critical-rules pointers name coding-os; link test covers commands
- 2026-11-24 [claude]: Tokens/session, fastapi scaffold, chars/4: before 22293, after 21208 (-1085)
- 2026-11-24 [claude]: AGENTS.md 3148 -> 3109; always-loaded rules 11948 -> 10902; skill listing 7197 -> 7197
- 2026-11-24 [claude]: docs/ read on demand: 44251 -> 24243 (-20008)
- 2026-11-24 [claude]: Note: the two earlier token lines were cut at the 120-char cap; these carry the numbers
- 2026-11-24 [claude]: commit bb1edae0c2 — docs(scaffold): rag-config no longer names the removed thinking_os origin spec
- 2026-11-24 [claude]: Status transitioned to complete via cos task-done.
