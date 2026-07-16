---
id: TASK-151
title: "Align docs to B0 skill fixes — memory.md read recipe + core-loop template + final-edition tool names"
swimlane: core
kind: docs
epic: skills-enterprise-hardening
labels: [skills, docs-alignment, drift, epic:skills-enterprise-hardening, ready]
status: archive
priority: P2
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-151: Align docs to B0 skill fixes — memory.md read recipe + core-loop template + final-edition tool names

**Outcome (one sentence):** The three agent-facing docs that drifted with the same fictional cos_* signatures B0 fixed are corrected: rules/memory.md read recipe uses real cos_learn_suggest(domain,complexity)/cos_timeline(days); core-loop.md.tmpl + thinking_os-final-edition.md use cos_search/cos_details/cos_health instead of the unregistered thinking_os_* names. The drift-guard test stays green.

## Read First
- src/core/rules/memory.md
- src/templates/_base/fragments/core-loop.md.tmpl
- src/core/docs/thinking_os-final-edition.md

## Work Log
- 2026-06-05 [claude]: Done (commit f61c364): aligned rules/memory.md read recipe (cos_learn_suggest domain/complexity, cos_timeline days), cor
