---
id: TASK-501
title: "Gate module-tool references in shipped governance docs (modularity DOC-3)"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-21
started: 2026-06-21
completed: 2026-06-21
agent_session: ses-claude-20260620-223048-0760
depends_on: []
blocked_by: []
references: []
---
# TASK-501: Gate module-tool references in shipped governance docs (modularity DOC-3)

**Outcome (one sentence):** A consumer that ran cos init --disable-module graph|memory gets shipped governance docs whose graph/memory tool sections are stripped, so cos_doc_search never returns guidance to call a runtime-gated tool.

## Read First
- src/templates/_base/scaffold/docs/governance/mcp-tool-inventory.md
- src/templates/_base/scaffold/docs/governance/agent-workflow.md
- src/cli/main.py
- docs/engineering/modularity-audit-2026-06.md

## Repro Steps
1. Scaffold a consumer with `cos init --disable-module graph` (and/or `memory`).
2. Run `cos_doc_search "graph references"` against the scaffolded docs/governance/.
Expected: no chunk instructs the agent to call cos_graph_* — the module is off.
Actual: the shipped governance docs (mcp-tool-inventory.md, agent-workflow.md) carry the graph/memory tool sections un-gated (no `module:` tag, no `<!-- if-module -->` block), so cos_doc_search returns guidance to call a runtime-gated tool that then fail('module_disabled')s.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a consumer scaffolded with `cos init --disable-module graph`
**When** cos_doc_search runs against the shipped mcp-tool-inventory.md / agent-workflow.md
**Then** no returned chunk instructs cos_graph_* tools, AND an all-modules-on scaffold of the same docs is byte-identical to today (only if-module markers stripped), AND the fix reuses the existing `_apply_doc_conditions` init path with no new schema axis.

## Work Log
- 2026-06-21 [claude]: Edit mcp-tool-inventory.md
- 2026-06-21 [claude]: Edit mcp-tool-inventory.md
- 2026-06-21 [claude]: Edit agent-workflow.md
- 2026-06-21 [claude]: Edit agent-workflow.md
- 2026-06-21 [claude]: Edit verify_doc501.py
- 2026-06-21 [claude]: commit 0094051e7a — docs(modularity): gate module-tool refs in shipped governance docs by owning module (TASK-501)
- 2026-06-21 [claude]: Gated mcp-tool-inventory.md + agent-workflow.md tool families in if-module blocks…
