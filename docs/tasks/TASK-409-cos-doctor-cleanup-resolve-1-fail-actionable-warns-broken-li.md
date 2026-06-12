---
id: TASK-409
title: "cos doctor cleanup \u2014 resolve 1 FAIL + actionable WARNs (broken link, legacy Go kind, PostToolUse task-move matcher, Sigma zero-width)"
swimlane: core
kind: bug
epic: null
labels: [doctor, graph-os, adapters, hub-ui, ready]
status: in_progress
priority: P2
appetite: 1d
created: 2026-06-12
started: 2026-06-12
completed: null
agent_session: ses-claude-20260611-002926-83d4
depends_on: []
blocked_by: []
references: []
---
# TASK-409: cos doctor cleanup — resolve 1 FAIL + actionable WARNs (broken link, legacy Go kind, PostToolUse task-move matcher, Sigma zero-width)

---
id: TASK-409
title: "cos doctor cleanup — resolve 1 FAIL + actionable WARNs (broken link, legacy Go kind, PostToolUse task-move matcher, Sigma zero-width)"
swimlane: core
kind: bug
epic: null
labels: [doctor, graph-os, adapters, hub-ui, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-12
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-409: cos doctor cleanup — resolve 1 FAIL + actionable WARNs (broken link, legacy Go kind, PostToolUse task-move matcher, Sigma zero-width)

**Outcome (one sentence):** cos doctor is clean of the agent-fixable findings — broken README link (FAIL), legacy Go `code:package` kind, hook.coverage zero-adapter for sync-task-current, the recurring Sigma zero-width client error, and the oversized WAL — while transient/environmental WARNs (embedding migration, DB size, optional extra, aging 24h errors) are reported with the exact clearing action rather than papered over.

## Read First
- src/cli/doctor.py
- src/cli/doctor_extras.py
- src/core/graph_os/types.py
- src/core/graph_os/extractors/code_go.py
- src/adapters/claude/adapter.yaml
- src/core/web/ui/src/features/graph/useSigma.ts

## Repro Steps
1. Run `cos doctor` on the meta-repo.
2. Observe summary: `46 PASS, 7 WARN, 1 FAIL (exit=1)`.
Expected: no FAIL, and no agent-fixable WARN (only genuinely transient/environmental ones, each with a stated clearing action).
Actual: FAIL `docs.markdown_link_integrity` (README → deleted `intent-vocabulary.md`); WARN `graph.legacy_kinds` (1 node `code:package:go:main`); WARN `hook.coverage` (sync-task-current PostToolUse/cos_task_move renders for zero adapters → `.task-current` never auto-syncs after an MCP move); WARN `runtime.recent_errors` (incl. recurring Sigma "Container has no width"); WARN `state.size_within_budget` (WAL over 50 MB).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the meta-repo after `cos graph-reindex --rebuild-kinds`, an MCP restart, and a `PRAGMA wal_checkpoint(TRUNCATE)`
- **When** `cos doctor` is re-run
- **Then** `docs.markdown_link_integrity` is PASS (stale README row removed), `graph.legacy_kinds` is PASS (the Go package node is canonical `module`, bridged in `_LEGACY_KIND_MAP` and emitted canonically by the Go extractor), `hook.coverage` is PASS (Claude adapter PostToolUse lists `mcp__coding-os__cos_task_move`, templates regenerated, `.claude/` re-rendered), `state.size_within_budget` WAL finding is gone, and the only remaining WARNs are the embedding migration (in progress), DB size (inflated by that migration), the optional dev extra, and historical 24h errors — each reported with its clearing action. Verified: graph_os + adapter suites green, vitest + ui-build green, `cos doctor` re-run shows the reduced count.

## Work Log
- 2026-06-12 [claude]: Edit types.py
- 2026-06-12 [claude]: Edit code_go.py
- 2026-06-12 [claude]: Edit code_go.py
- 2026-06-12 [claude]: Edit adapter.yaml
- 2026-06-12 [claude]: Edit useSigma.ts
- 2026-06-12 [claude]: Edit test_code_go.py
- 2026-06-12 [claude]: Fixed: README stale intent-vocabulary row removed (FAIL→PASS, 64 links resolve); Go package node emits canonical `module
