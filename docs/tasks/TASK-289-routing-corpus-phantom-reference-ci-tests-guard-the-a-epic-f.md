---
id: TASK-289
title: "Routing-corpus + phantom-reference CI tests (guard the A-epic fixes forever)"
swimlane: core
kind: test
epic: retrieval-routing-fix
labels: [routing, tests, ci-guard, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-09
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260609-143642-c7c5
depends_on: [TASK-284, TASK-285]
blocked_by: []
references: []
---
# TASK-289: Routing-corpus + phantom-reference CI tests (guard the A-epic fixes forever)

**Outcome (one sentence):** Two enterprise CI guards that would have caught the original bug. (1) Routing-corpus test: a YAML/py corpus of representative queries -> expected nudge tool (incl. the 9 measured cases: conceptual "how does graph work" + structural dead_code/test_gap), asserting nudge-graph-os routes each correctly; fails if coverage regresses. Produces a measured coverage % (the empirical score the user asked for). (2) Phantom-reference contract test: scans every cos_* token in docs/**, src/core/rules/**, src/core/skills/** and asserts each names a REGISTERED MCP tool — fails on any dangling ref like the old cos_retrieve. Both with structured output + progress reporting; improve test_hooks_* if a home exists, else create.

## Read First
- tests/test_hooks.py
- src/core/hooks/nudge-graph-os.sh
- src/core/thinking_os/server.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the A-epic fixes have landed (TASK-284 purge + reorder, TASK-285 expanded nudge).
- **When** the routing-corpus test runs the representative query set through nudge-graph-os, and the phantom-reference test scans every cos_* token in docs/**, src/core/rules/**, src/core/skills/** against the registered MCP tool set.
- **Then** routing coverage is reported as a measured % and is ≥95%, zero cos_* references resolve to an unregistered tool (the old cos_retrieve would FAIL this), both tests fail loudly on regression, emit structured output with progress, and pass under `uv run pytest`.

## Work Log
- 2026-06-09 [claude]: Added tests/test_nudge_graph_routing.py (26-query corpus, invokes real hook, isolated panel dirs, parametrized=progress;
