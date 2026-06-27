---
id: TASK-596
title: "seed .editorconfig + base .gitignore in _base/scaffold (universal format primitive)"
swimlane: templates
kind: chore
epic: stack-factory-v2
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-27
started: 2026-06-26
completed: 2026-06-26
agent_session: ses-claude-20260626-165558-a565
depends_on: []
blocked_by: []
references: []
---
# TASK-596: seed .editorconfig + base .gitignore in _base/scaffold (universal format primitive)

**Outcome (one sentence):** Every project from `cos init` inherits a language-agnostic `.editorconfig` and a base `.gitignore` from `_base/scaffold`. Verified absent today; this is the single highest-reach diff — it reaches all 26 stacks at once and makes `dotnet format` (which reads .editorconfig) meaningful. Raptor: one _base file, zero per-stack variance.

## Work Log
- 2026-06-27 [claude]: Edit .editorconfig
- 2026-06-27 [claude]: Edit .gitignore
- 2026-06-27 [claude]: Status transitioned to complete via cos task-done.
