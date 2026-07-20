---
id: TASK-452
title: "B-5/B-6 fix: gate Core-Loop/Handoff tool refs on their module (F2 coverage + RGC-B coherence)"
swimlane: templates
kind: refactor
epic: null
labels: [modularity-audit-pass3, F2, RGC-B, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-19
started: 2026-06-19
completed: 2026-06-19
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-452: B-5/B-6 fix: gate Core-Loop/Handoff tool refs on their module (F2 coverage + RGC-B coherence)

**Outcome (one sentence):** The rendered consumer AGENTS.md no longer commands a tool whose subsystem is disabled — core-loop.md.tmpl gates the Orient Memory Check + cos_learn_extract on modules.memory and cos_metric_record on modules.observability; session-handoff.md.tmpl gates cos_learn_narrative + Memory Check on modules.memory. Audit-honest scope: graph/cognition/hub-extras carry NO always-on AGENTS.md prose (their surface is the loaded skill + the MCP gate), so disabling them correctly strips nothing — F2's '5/8 modules contribute no prose' is correct-by-design for those, not a gap to paper over with invented prose (Raptor). Default (all-on) render is byte-identical (golden-parity unchanged).

## Read First
- src/templates/_base/fragments/core-loop.md.tmpl
- src/templates/_base/fragments/session-handoff.md.tmpl
- tests/test_all_stacks_render_smoke.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** AGENTS.md rendered with the memory module disabled **When** inspected **Then** "Memory Check", cos_learn_extract and cos_learn_narrative are absent, cos_metric_record is present, and the output is Jinja-clean.
- **Given** AGENTS.md rendered with observability disabled **When** inspected **Then** cos_metric_record is absent while Memory Check + cos_learn_extract remain.
- **Given** all modules on (default) **When** rendered **Then** the output is byte-identical to the golden (test_golden_parity green).

## Work Log
- 2026-06-19 [claude]: commit 6f1156a3b2 — refactor(templates): gate Core-Loop/Handoff tool refs on their module (F2/RGC-B)
- 2026-06-19 [claude]: Edit _resources.py
- 2026-06-19 [claude]: Edit _resources.py
- 2026-06-19 [claude]: Edit stack_registry.py
- 2026-06-19 [claude]: Edit adapter_registry.py
- 2026-06-19 [claude]: Edit stack_registry.py
- 2026-06-19 [claude]: Edit adapter_registry.py
- 2026-06-19 [claude]: Edit stack_lint.py
- 2026-06-19 [claude]: Edit test_stack_registry.py
- 2026-06-19 [claude]: Edit test_adapter_registry.py
- 2026-06-19 [claude]: Edit test_adapter_registry.py
