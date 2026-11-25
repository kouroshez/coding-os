---
id: TASK-1127
title: "spike(scaffold): measure what duplication and always-on token cost a fresh consumer scaffold still carries"
swimlane: templates
kind: spike
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-11-25
started: 2026-11-24
completed: 2026-11-24
agent_session: ses-claude-20261124-204737-f93d
depends_on: []
blocked_by: []
references: []
---
# TASK-1127: spike(scaffold): measure what duplication and always-on token cost a fresh consumer scaffold still carries

**Outcome (one sentence):** A measured account of how much repeated text and always-on context a fresh cos init project still carries after TASK-1119/1120, with each remaining duplicate named by file.

## Read First
- src/cli/_init_scaffold.py
- src/core/scaffold_manifest.json
- docs/architecture/meta-project.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a fresh fastapi scaffold, **When** files, always-on tokens and repeated paragraphs are measured, **Then** each figure is recorded in the Work Log with the command that produced it.
- **Given** a repeated paragraph, **When** it is reported, **Then** the files holding it are named.

## Work Log
- 2026-11-25 [claude]: fresh fastapi scaffold (cos init -a claude,codex -t fastapi): 677 files 4.3MB; skills copied in .claude and .codex
- 2026-11-25 [claude]: always-on chars/4: AGENTS.md 3110 + 8 rules 10988 + skill list 7068 = ~21.2k, same as TASK-1120 after
- 2026-11-25 [claude]: AGENTS.md: make task-done drops WHAT/FILES; make task-create prints help; hand-Edit fallback vs task hook
- 2026-11-25 [claude]: rules: api-contract + timestamp point at src/core/** (absent in consumer); banner rule ~2.2k tok of internals
- 2026-11-25 [claude]: 54 repeated paragraphs, mostly 9 role-* commands (on demand); docs index links to absent example pages
- 2026-11-25 [claude]: Status transitioned to complete via cos task-done.
