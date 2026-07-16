---
id: TASK-260
title: "Hub trace + task-modal polish (classify node, modal hardening)"
swimlane: core
kind: chore
epic: hub-redesign
labels: [traces, modal, hub, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-20260608-021813-db02
depends_on: []
blocked_by: []
references: []
---
# TASK-260: Hub trace + task-modal polish (classify node, modal hardening)

**Outcome (one sentence):** Plan EPIC C-core + D follow-ups: (S8-core) map the `classify` trace kind to the n-gate flowchart node so the Complexity Gate event phases as Setup instead of surfacing as a raw "unknown" chip; (S12) harden the task-detail modal (z-index alignment, rename TaskDetailDrawer→TaskDetailModal, aria-label on close, collapsible history, a Move action) — the centered modal itself already shipped (TASK-172). Plan: /tmp/cos-board-envelope-and-hub-plan.md.

## Work Log
- 2026-06-08 [claude]: S8-core (701e4dbe): mapped classify->n-gate in FLOWCHART_NODES so the Complexity Gate event phases as Setup, not a raw '
