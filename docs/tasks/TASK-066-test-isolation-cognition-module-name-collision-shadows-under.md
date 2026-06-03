---
id: TASK-066
title: "Test-isolation: cognition module-name collision shadows under flat sys.path (auto_compose import)"
swimlane: thinking_os
kind: bug
epic: null
labels: []
status: icebox
priority: P3
appetite: "1d"
created: 2026-06-03
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-066: Test-isolation: cognition module-name collision shadows under flat sys.path (auto_compose import)

**Outcome (one sentence):** Pre-existing latent test-isolation fragility surfaced by TASK-065. Two modules named cognition.py exist: src/core/thinking_os/cognition.py (owns load_situation_registry) and src/core/thinking_os/tools/cognition.py (does bare `import cognition as _mod` expecting the former). The auto_compose.py hook helper inserts thinking_os/tools ahead of thinking_os on sys.path; any in-process import of auto_compose (e.g. test_compose_trace_wiring) can make a bare `import cognition` resolve to tools/cognition.py, breaking cos_situation_detect (AttributeError: no load_situation_registry). Only manifests under certain pytest collection orders; the full thinking_os suite (1266) passes in stable order, so it is non-blocking. Proper fix = remove the bare-name collision (rename one module OR make tools/cognition.py import package-qualified core.thinking_os.cognition), not test band-aids. Repro: pytest test_compose_trace_wiring.py test_cognition_tools.py (9 TestCosSituationDetect failures).

## Read First
- src/core/thinking_os/tools/cognition.py
- src/core/thinking_os/cognition.py
- src/core/hooks/_helpers/auto_compose.py

## Repro Steps
1. (fill in: exact steps to reproduce)
2. ...
Expected: ...
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
