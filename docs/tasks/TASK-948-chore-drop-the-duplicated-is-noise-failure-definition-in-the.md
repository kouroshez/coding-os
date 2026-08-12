---
id: TASK-948
title: "chore: drop the duplicated _is_noise_failure definition in the friction miner"
swimlane: "thinking_os"
kind: chore
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-12
started: 2026-08-12
completed: 2026-08-12
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-948: chore: drop the duplicated _is_noise_failure definition in the friction miner

**Outcome (one sentence):** _learning_mining.py defines _is_noise_failure once, so a future edit to the noise filter cannot land on the shadowed copy and silently do nothing.

## Work Log
- 2026-08-12 [claude]: commit 00920e94f7 — chore(thinking_os): drop a shadowed duplicate of _is_noise_failure
- 2026-08-12 [claude]: Two identical defs collapsed to one; 1572 thinking_os tests green; ruff clean.
- 2026-08-12 [claude]: Status transitioned to complete via cos task-done.
