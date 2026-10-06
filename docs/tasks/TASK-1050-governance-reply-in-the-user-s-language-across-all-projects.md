---
id: TASK-1050
title: "governance: reply in the user's language across all projects"
swimlane: infra
kind: chore
epic: null
labels: [governance, ready]
status: complete
priority: P1
appetite: 1h
created: 2026-10-05
started: 2026-10-05
completed: 2026-10-05
agent_session: ses-claude-20261004-231222-9711
depends_on: []
blocked_by: []
references: []
---
# TASK-1050: governance: reply in the user's language across all projects

**Outcome (one sentence):** Every user-visible reply follows the language of the user's latest message in every project, enforced by one short section in the global CLAUDE.md plus a feedback memory, so a long English-heavy session no longer drifts into English.

## Work Log
- 2026-10-05 [claude]: Edit CLAUDE.md
- 2026-10-05 [claude]: commit ffa7eaf093 — chore(memory): record that replies follow the user's language
- 2026-10-05 [claude]: Root cause: no setting or rule forced English; replies drifted under English-heavy hook/agent context. Fix: "Reply…
- 2026-10-05 [claude]: Status transitioned to complete via cos task-done.
