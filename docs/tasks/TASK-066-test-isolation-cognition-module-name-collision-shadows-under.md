---
id: TASK-066
title: "Test-isolation: cognition module-name collision shadows under flat sys.path (auto_compose import)"
swimlane: thinking_os
kind: bug
epic: null
labels: []
status: complete
priority: P3
appetite: "1d"
created: 2026-06-03
started: 2026-06-03
completed: 2026-06-03
agent_session: ses-claude-20260527-151803-0b9f
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
1. `uv run --extra rag pytest src/core/thinking_os/tests/test_compose_trace_wiring.py src/core/thinking_os/tests/test_cognition_tools.py -q`
Expected: all pass.
Actual (before fix): 9 `TestCosSituationDetect` failures — `KeyError: 'data'` / AttributeError, because importing `auto_compose` put `thinking_os/tools` ahead of `thinking_os` on sys.path, so `tools/cognition.py::_cog`'s bare `import cognition` shadowed to itself (no `load_situation_registry`).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `auto_compose` is imported in the same process as other thinking_os modules,
- **When** `tools/cognition.py::_cog` does `import cognition`,
- **Then** it always resolves to top-level `thinking_os/cognition.py` (owns `load_situation_registry`) — because `auto_compose` no longer adds the `thinking_os/tools` package dir to sys.path flat and imports `learning` package-qualified (`from tools.learning import ...`); the repro command passes, the full thinking_os suite stays green, and a regression test asserts the import order no longer shadows. Deeper dual-name elimination (rename) deferred as defense-in-depth, not required for this fix.

## Work Log
- 2026-06-03 [claude]: Fix A shipped: auto_compose adds only thinking_os to sys.path + imports learning package-qualified. Shadow gone. Repro 2
