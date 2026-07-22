---
id: TASK-512
title: "Fix governance-doc links into gitignored .claude/ (docs-lint broken-file gate)"
swimlane: docs
kind: docs
epic: null
labels: [docs-update, ci, docs-lint, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-21
started: 2026-06-21
completed: 2026-06-22
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-512: Fix governance-doc links into gitignored .claude/ (docs-lint broken-file gate)

**Outcome (one sentence):** AGENTS.md and constitution.md link to committed src/templates/meta/rules/ sources instead of gitignored .claude/rules/, so docs-lint's BROKEN-FILE hard gate passes on a clean clone.

## Read First
- src/core/scripts/docs-lint.sh
- docs/governance/constitution.md

## Work Log
- 2026-06-21 [claude]: Edit AGENTS.md
- 2026-06-21 [claude]: commit ec33d285c8 — docs: repoint AGENTS.md + constitution.md links to committed rule sources
- 2026-06-22 [claude]: Status transitioned to complete via cos task-done.
