---
id: TASK-1052
title: "Bind graph-reindex -j worker lifetime to the parent so a killed reindex leaves no orphans"
swimlane: cli
kind: bug
epic: null
labels: ["graph_os", cli, resource-leak, ready]
status: testing
priority: P1
appetite: 1d
created: 2026-10-07
started: 2026-10-07
completed: null
agent_session: ses-claude-20261007-140442-890a
depends_on: []
blocked_by: []
references: []
---
# TASK-1052: Bind graph-reindex -j worker lifetime to the parent so a killed reindex leaves no orphans

**Outcome (one sentence):** When `cos graph-reindex -j N` dies by SIGKILL/SIGTERM/terminal close, its ProcessPoolExecutor workers and resource_tracker exit within ~2s instead of spinning orphaned (PPID 1) at ~97% CPU and holding deleted multi-GB WAL files open.

## Read First
- src/cli/_graph_cli_reindex.py

## Repro Steps
Observed 2026-10-07: two orphan groups (10 procs, PPID 1) from `graph-reindex -j 4` runs whose parent was proc.kill()-ed by a watch harness; one worker per group at 92-97% CPU in sqlite3_step for 18+ min, holding a deleted 9.5 GB and 2.2 GB coding-os.db-wal. Repro: start `cos graph-reindex --path <corpus> -j 4 --force`, `kill -9 <parent>`, `ps -axo ppid,command | awk '$1==1 && /multiprocessing/'`.

## Spec
ProcessPoolExecutor workers only notice a dead parent after their current task returns, and a task can run for minutes (one ran 18+ min). The pool is built with an initializer that starts a daemon thread in each worker: it polls `os.getppid()` once a second and calls `os._exit` as soon as the parent pid changes. sqlite3 and tree-sitter release the GIL in C, so the thread can run while the main thread is busy. The resource_tracker exits by itself once the last worker closes its pipe. macOS has no `PR_SET_PDEATHSIG`, so polling is the portable form. `_graph_cli_reindex.py` is at its 500-line budget, so the pool factory lives in its own module.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a running `graph-reindex -j 4`, **When** the parent gets SIGKILL, **Then** every worker and the resource_tracker exit within 3s.
- **Given** a running `graph-reindex -j 4`, **When** the parent gets SIGTERM, **Then** no multiprocessing process survives 3s later.
- **Given** a normal `graph-reindex -j 4` run, **When** it completes, **Then** it indexes the same files as the sequential path and no worker survives.
- **Given** the watchdog, **When** the parent is alive, **Then** the worker is never killed (no false positives) and its idle cost is one getppid per second.

## Work Log
- 2026-10-07 [claude]: Plan: pool initializer starts a getppid-polling daemon thread that os._exit()s on parent change; parent read inside…
- 2026-10-07 [claude]: Edit _parent_bound_pool.py
- 2026-10-07 [claude]: Edit _graph_cli_reindex.py
- 2026-10-07 [claude]: Edit test_parent_bound_pool.py
- 2026-10-07 [claude]: Edit _parent_bound_pool.py
- 2026-10-07 [claude]: Edit test_parent_bound_pool.py
- 2026-10-07 [claude]: Edit _parent_bound_pool.py
- 2026-10-07 [claude]: Edit _parent_bound_pool.py
- 2026-10-07 [claude]: Verified: plain pool repro left 4 PPID-1 orphans after SIGKILL; fixed pool — tests/test_parent_bound_pool.py 5/5,…
