---
id: TASK-715
title: "Derived-store coherence: prune-on-delete + GC wiring across DB read-models"
swimlane: infra
kind: chore
epic: null
labels: [ready]
status: in_progress
priority: P2
appetite: 1d
created: 2026-06-30
started: 2026-06-30
completed: null
agent_session: ses-claude-20260628-125542-fc9a
depends_on: []
blocked_by: []
references: []
---
# TASK-715: Derived-store coherence: prune-on-delete + GC wiring across DB read-models

**Outcome (one sentence):** Close the derived-store drift class — task rows + their child tables prune when a task file is deleted, doc-chunk orphans and orphan embeddings are GC'd nightly, and hook BLOCK events stop being mis-filed as bugs by error_sweep.

**Read First:** docs/engineering/derived-store-coherence-audit-2026-06-30.md · src/core/board_os/sync.py · src/core/scheduled/nightly.py · src/core/thinking_os/database.py · src/core/scheduled/error_sweep.py

**Acceptance:**

- A deleted task file prunes its `tasks` row on full sync, cascading to task_status_history / task_outcomes / task_edit_history (no orphan rows; no panel ghost).
- A deleted doc file's `document_chunks` are pruned by a nightly reconcile.
- `memory_gc()` runs in the nightly (orphan embeddings + trash observations reclaimed).
- error_sweep files only genuine faults; hook BLOCK events (`policy` class) are never filed.
- Each fix verified by its Verification-Matrix suite + a live simulation.

## Work Log
- 2026-06-30 [claude]: Edit derived-store-coherence-audit-2026-06-30.md
- 2026-06-30 [claude]: Edit database.py
- 2026-06-30 [claude]: Edit database.py
- 2026-06-30 [claude]: Edit sync.py
- 2026-06-30 [claude]: Edit sim_fix1.py
- 2026-06-30 [claude]: Edit sim_fix1.py
- 2026-06-30 [claude]: Edit sim_fix1.py
- 2026-06-30 [claude]: Edit sim_fix1.py
- 2026-06-30 [claude]: Edit sim_fix1.py
- 2026-06-30 [claude]: Edit test_sync.py
- 2026-06-30 [claude]: Edit test_sync.py
