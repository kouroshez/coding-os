---
id: TASK-848
title: "coding-os health remediation: green the doctor (governance \u2014 hooks, doctor-config, graph/state)"
swimlane: core
kind: chore
epic: null
labels: []
status: archive
priority: P2
appetite: 1d
created: 2026-07-22
started: 2026-07-22
completed: 2026-07-21
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-848: coding-os health remediation: green the doctor (governance — hooks, doctor-config, graph/state)

**Outcome (one sentence):** cos doctor goes from 4 FAIL / 4 WARN to 0 FAIL / 3 legitimate WARN — the declared memory hooks resolve via adapter_scope, non-exec hooks are executable, placeholder false-positives skipped, dead hub entries + stray root templates/ leftover + stale backup removed.

## Acceptance
1. **Given** the 2 memory hooks declared with adapter_scope:claude living in src/adapters/claude/hooks/, **When** `cos doctor` runs, **Then** hook.coverage and adapter.configured pass.
2. **Given** docs/tasks files that quote {{PROJECT_NAME}} as subject matter, **When** the placeholder scan runs, **Then** scaffold.placeholders_resolved passes.
3. **Given** the stray untracked root templates/ dir, dead hub registry entries, and 307M stale backup, **When** `cos doctor` re-runs, **Then** graph.uid_consistency + hub.project_paths_exist pass and the summary is 0 FAIL.

## Work Log
- 2026-07-22 [claude]: Edit doctor-config.yaml
- 2026-07-22 [claude]: Edit doctor.py
- 2026-07-22 [claude]: Two reuse-first pivots avoided wrong fixes: (1) the '2 missing hooks' were NOT missing —…
- 2026-07-22 [claude]: committed 5b7b2cc1 · 5 files
- 2026-07-22 [claude]: Status transitioned to complete via cos task-done.
