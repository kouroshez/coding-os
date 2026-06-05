---
id: TASK-142
title: "EM-DESIGN: Extension Manager architecture + security/trust model design doc (contract before code)"
swimlane: core
kind: spike
epic: extension-manager
labels: [extension-manager, design, hub, data-driven, epic:extension-manager, ready]
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

# TASK-142: EM-DESIGN: Extension Manager architecture + security/trust model design doc (contract before code)

**Outcome (one sentence):** A design doc (docs/engineering/extension-manager.md) is the SSOT contract for add/remove/upload of skills+MCP from the Hub panel: unified CatalogUnit model, per-project extensions.json manifest, trust state machine, fail-closed security gate (SKILL.md injection scan, MCP allow-list URL-preferred, upload jail, Hub auth), API + UI surface, adapter-parity fan-out, phased P0-P5 plan. v1 scope = skills + MCP (hooks/rules/commands read-only). No code ships until reviewed.

## Work Log
