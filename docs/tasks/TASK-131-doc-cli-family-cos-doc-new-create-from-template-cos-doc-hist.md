---
id: TASK-131
title: "Doc CLI family — cos doc-new (create from template) + cos doc-history (git versions) + cos doc-lint single-file"
swimlane: cli
kind: feature
epic: doc-system
labels: [docs-system, cli, tooling, audit-d4-f1, ready]
status: icebox
priority: P2
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-131: Doc CLI family — cos doc-new (create from template) + cos doc-history (git versions) + cos doc-lint single-file

**Outcome (one sentence):** Three thin CLI surfaces so doc lifecycle is tool-driven not hand-copied: cos doc-new --layer L --path P scaffolds correct frontmatter+opening-block+nav from the template (D4-F1); cos doc-history <path> shells git log --follow + show to answer 'show me prior versions of this doc' (D4-F2, the user's explicit git-version ask); cos doc-lint <path> validates one doc via the existing docs-lint single-file arg (D4-F4). Reuse docs-lint.sh + templates; no new parsers.

## Read First
- docs/tasks/audits/audit-doc-system-2026-06-05.md
- src/cli/main.py
- src/core/scripts/docs-lint.sh
- docs/governance/_templates/doc-cheat-sheet.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
