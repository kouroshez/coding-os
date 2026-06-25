---
id: TASK-577
title: "Cluster 4 \u2014 Consolidate to one graph-gate.sh (merge 4 enforce hooks) + one ordered auto-graph-reconcile-shell.sh, with consumer migration + golden regen + parity test"
swimlane: core
kind: refactor
epic: graph-first-enforcement
labels: [hooks, consolidation, migration, golden, graph-gate, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-25
started: null
completed: null
agent_session: null
depends_on: [TASK-573, TASK-574, TASK-575]
blocked_by: []
references: []
---

# TASK-577: Cluster 4 — Consolidate to one graph-gate.sh (merge 4 enforce hooks) + one ordered auto-graph-reconcile-shell.sh, with consumer migration + golden regen + parity test

**Outcome (one sentence):** enforce-graph-context + enforce-graph-first-read + enforce-rename-plan + verify-rename-callers collapse into one event-keyed graph-gate.sh (PreToolUse Read|Write|Edit + PostToolUse Edit) sharing one helper invocation and the single .graph/ marker namespace; auto-reindex-shell-ops + auto-prune-deleted-files merge into one ordered auto-graph-reconcile-shell.sh (tokenize once, prune-if-gone THEN reindex-if-present, fixing the N10 race). registry.yaml is the SSOT; golden adapter templates regen; an SM6 migration sweeps old-namespace markers and a parity test asserts no consumer breakage. Net: 8 graph hooks -> 5, 4 marker schemes -> 1. Closes N10, the 4->1 consolidation, D3 (render), SM6.

## Read First
- src/core/hooks/registry.yaml
- src/core/hooks/enforce-graph-context.sh
- src/core/hooks/enforce-graph-first-read.sh
- src/core/hooks/enforce-rename-plan.sh
- src/core/hooks/auto-reindex-shell-ops.sh
- src/core/hooks/auto-prune-deleted-files.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
GIVEN the consolidation WHEN make verify-hooks runs THEN graph-gate.sh + auto-graph-reconcile-shell.sh pass shellcheck and smoke; GIVEN a consumer carrying old-namespace markers THEN the migration sweeps them with no spurious re-block; AND registry.yaml is the single registration source; AND make regen-adapter-templates + golden regen are green; AND tests/test_adapter_parity.py + verify-hooks green.

## Work Log
