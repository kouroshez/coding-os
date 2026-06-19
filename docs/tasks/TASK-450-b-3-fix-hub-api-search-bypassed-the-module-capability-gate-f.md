---
id: TASK-450
title: "B-3 fix: Hub /api/search/* bypassed the module capability gate (F1 consumer-path hole)"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [modularity-audit-pass3, hub, F1, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-19
started: 2026-06-19
completed: 2026-06-19
agent_session: ses-claude-20260619-063923-1c50
depends_on: []
blocked_by: []
references: []
---
# TASK-450: B-3 fix: Hub /api/search/* bypassed the module capability gate (F1 consumer-path hole)

**Outcome (one sentence):** The Hub HTTP search routes (/api/search/memory, /docs, /tasks) now honor the same subsystem toggle the MCP cos_search/cos_doc_search/cos_task_search tools do, scoped to the request's project. Before: the routes imported tools.memory/docs/tasks directly and never called _gated_module, which in any case reads $COS_STATE_DIR (wrong project under the multi-project Hub) — so a disabled memory/docs/tasks module still served results over the web API (audit F1). Fix reuses cli.subsystems.module_state(current_project_root()); a disabled module returns a module_disabled envelope mapped to HTTP 403.

## Read First
- src/core/web/routes/search.py
- src/core/web/_envelope.py
- src/core/thinking_os/tools/_shared.py
- src/cli/subsystems.py

## Repro Steps
Disable the memory module, start the Hub, GET /api/search/memory?query=x — pre-fix returns 200 memory results (gate bypassed); post-fix returns 403 module_disabled.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a project with subsystems-state.json disabling memory and COS_PROJECT_ROOT set to it **When** GET /api/search/memory?query=x **Then** HTTP 403 with error.category=module_disabled naming memory. - **Given** only memory disabled **When** GET /api/search/docs **Then** not 403 (each route gates on its own module). - **Given** TestSearchRoutes **When** run **Then** all pass (5 incl 2 new).

## Work Log
- 2026-06-19 [claude]: committed 9dcad28d · 3 files
- 2026-06-19 [claude]: Edit record_outcome.py
- 2026-06-19 [claude]: Edit record_outcome.py
- 2026-06-19 [claude]: Edit record_outcome.py
- 2026-06-19 [claude]: Edit test_record_outcome.py
- 2026-06-19 [claude]: Edit test_record_outcome.py
