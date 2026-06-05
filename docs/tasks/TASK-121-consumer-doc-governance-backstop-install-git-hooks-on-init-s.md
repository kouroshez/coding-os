---
id: TASK-121
title: "Consumer doc-governance backstop — install git hooks on init + ship docs-lint CI + consumer-aware staleness-check + fix master-index dead link"
swimlane: infra
kind: feature
epic: doc-system
labels: [docs-system, dogfood, enforcement, ci, audit-d5-f6, ready]
status: icebox
priority: P1
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-121: Consumer doc-governance backstop — install git hooks on init + ship docs-lint CI + consumer-aware staleness-check + fix master-index dead link

**Outcome (one sentence):** Every cos init consumer gets git pre-commit/commit-msg installed (idempotent), a minimal docs-lint CI workflow in scaffold/.github/, a docs-staleness-check that audits the CONSUMER's docs not the meta-repo internals (D6-F6), and a docs/00-index.md without the retired ./tasks.md dead link (D6-F2) — so human/Codex-GUI doc edits are governed from day one (D5-F6, D7-F7).

## Read First
- docs/tasks/audits/audit-doc-system-2026-06-05.md
- src/cli/_init_helpers.py
- src/scripts/install-git-hooks.sh
- src/templates/_base/scaffold/docs/00-index.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
