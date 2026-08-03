---
id: TASK-865
title: "Module toggle consistency audit: instructions/rules/hooks auto-align in consumer projects"
swimlane: core
kind: chore
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-03
started: 2026-08-03
completed: 2026-08-03
agent_session: ses-claude-20260803-153956-0acf
depends_on: []
blocked_by: []
references: []
---
# TASK-865: Module toggle consistency audit: instructions/rules/hooks auto-align in consumer projects

**Outcome (one sentence):** A consumer project with any module subset (down to kernel-only, no hub) works unbroken, and AGENTS.md / rules / hooks / skills automatically gain and lose their module-specific instructions on every enable/disable — gaps found in this audit are fixed.

## Read First

- src/core/subsystems.yaml — module ownership SSOT
- src/cli/subsystems.py + src/cli/module_commands.py — toggle implementation
- src/cli/aggregator.py / config_composer.py — AGENTS.md rendering
- src/core/scripts/install-adapter.sh + extract_disabled_module_rules.py

## Acceptance (G/W/T)

- Given a scratch consumer project, when a module is disabled, then its hooks self-skip, its skills unlink, its rules unlink, and the agent instructions no longer tell the agent to use that module's commands/tools.
- Given kernel-only (all optional modules off, no hub), when the agent works, then no instruction references tasks/graph/memory workflows and nothing crashes.
- Given re-enable, then everything returns symmetrically.

## Work Log
- 2026-08-03 [claude]: Edit stop-conditions.md.tmpl
- 2026-08-03 [claude]: Edit verification-matrix.md.tmpl
- 2026-08-03 [claude]: Edit core-loop.md.tmpl
- 2026-08-03 [claude]: Edit core-loop.md.tmpl
- 2026-08-03 [claude]: Edit core-loop.md.tmpl
- 2026-08-03 [claude]: Edit core-loop.md.tmpl
- 2026-08-03 [claude]: Edit retrieval-routing.md.tmpl
- 2026-08-03 [claude]: Edit retrieval-routing.md.tmpl
- 2026-08-03 [claude]: Edit retrieval-routing.md.tmpl
- 2026-08-03 [claude]: Edit session-handoff.md.tmpl
- 2026-08-03 [claude]: Edit retrieval-routing.md.tmpl
- 2026-08-03 [claude]: commit 04ff621a38 — fix(templates): gate every task-system instruction in AGENTS.md fragments on modules.tasks
- 2026-08-03 [claude]: Deep audit executed on two real scratch consumer projects (cos init python stack). VERIFIED WORKING: module disable→…
- 2026-08-03 [claude]: Status transitioned to complete via cos task-done.
