---
id: TASK-1020
title: "Timestamp follow-ups \u2014 eslint headroom, consumer rule propagation, naive-TEXT column migration"
swimlane: core
kind: chore
epic: null
labels: [governance, docs-update, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-24
started: 2026-08-24
completed: 2026-08-24
agent_session: ses-claude-20260823-134429-13ad
depends_on: []
blocked_by: []
references: []
---
# TASK-1020: Timestamp follow-ups — eslint headroom, consumer rule propagation, naive-TEXT column migration

**Outcome (one sentence):** The eslint ratchet regains headroom so one new UI warning cannot re-lock a release; both registered consumers carry the timestamp rule; and the only genuinely illegal storage form left — naive TEXT from SQLite datetime('now') — is migrated to ISO-Z, with epoch INTEGER/REAL columns left alone because the contract already declares them legal.

## Work Log
- 2026-08-24 [claude]: commit 59946e2c46 — fix(ui): escape six JSX entities to give the eslint ratchet headroom
- 2026-08-24 [claude]: commit 42c865f928 — feat(db): migration v54 normalizes mixed TEXT timestamp columns to ISO-Z
- 2026-08-24 [claude]: commit d06da10a3b — fix(core): stop five writers emitting naive timestamps into migrated columns
- 2026-08-24 [claude]: commit 7ea7e7352e — docs(engineering): record why only half the naive-TEXT columns were migrated
- 2026-08-24 [claude]: commit d98ddec754 — feat(skills): add Persian/Arabic text normalization to the i18n skill
- 2026-08-24 [claude]: Migration scoped by evidence, not by the doc's earlier guess. Measured the live 342MB DB: formula_dispatches.ts held…
- 2026-08-24 [claude]: Deliberately migrated only half. The learning/memory/graph tables use SQLite's naive space-separated form…
- 2026-08-24 [claude]: Status transitioned to complete via cos task-done.
