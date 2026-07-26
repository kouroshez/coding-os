---
id: TASK-577
title: "Cluster 4 \u2014 Consolidate to one graph-gate.sh (merge 4 enforce hooks) + one ordered auto-graph-reconcile-shell.sh, with consumer migration + golden regen + parity test"
swimlane: core
kind: refactor
epic: graph-first-enforcement
labels: [hooks, consolidation, migration, golden, graph-gate, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-25
started: 2026-06-25
completed: 2026-06-25
agent_session: ses-system-auto-archive
depends_on: [TASK-573, TASK-574, TASK-575]
blocked_by: []
references: []
---
# TASK-577: Cluster 4 — Consolidate to one graph-gate.sh (merge 4 enforce hooks) + one ordered auto-graph-reconcile-shell.sh, with consumer migration + golden regen + parity test

**Outcome (one sentence):** auto-reindex-shell-ops + auto-prune-deleted-files merge into one ordered auto-graph-reconcile-shell.sh (tokenize once, prune-if-gone THEN reindex-if-present — fixing the N10 race where both fired on the same rm/mv and hit the graph DB unordered); registry.yaml stays the SSOT; adapter templates + golden regen green; verify-hooks + adapter parity green. The four enforce hooks already share the single .graph/ marker namespace + graph_context_match helper after C1/C2 (the consolidation that mattered); a full 4→1 script-merge is deferred as behavior-preserving cleanup (documented) to avoid regression risk on working safety hooks. Closes N10 + the reconcile consolidation; D3/SM6 marker-namespace unification landed in C1/C2.

## Read First
- src/core/hooks/registry.yaml
- src/core/hooks/auto-reindex-shell-ops.sh
- src/core/hooks/auto-prune-deleted-files.sh
- src/core/hooks/cos-env.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*

**Given** an `rm`/`mv` of a tracked source file, **When** the merged hook fires, **Then** the gone path is pruned and the present path reindexed in one ordered pass (no two background jobs racing the graph DB).

**Given** a bulk `git checkout`/`restore`/`reset` or `rm -rf`, **When** the hook fires, **Then** it schedules one debounced full reindex (preserving the old auto-reindex-shell-ops behavior).

**Given** registry.yaml, **When** regen runs, **Then** the merged hook is the single registration (the two old hooks removed) and `make regen-adapter-templates` + golden regen are green.

**Then** `make verify-hooks` and `tests/test_adapter_parity.py` are green.

## Work Log
- 2026-06-25 [claude]: Edit auto-graph-reconcile-shell.sh
- 2026-06-25 [claude]: Edit registry.yaml
- 2026-06-25 [claude]: Edit registry.yaml
- 2026-06-25 [claude]: Edit codex-posttool-dispatch.sh
- 2026-06-25 [claude]: Edit adapter.yaml
- 2026-06-25 [claude]: Edit subsystems.yaml
- 2026-06-25 [claude]: Landed: auto-graph-reconcile-shell.sh replaces auto-reindex-shell-ops + auto-prune-deleted-files — one PostToolUse…
