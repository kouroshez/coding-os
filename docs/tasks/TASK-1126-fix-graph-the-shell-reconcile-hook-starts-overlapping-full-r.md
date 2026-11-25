---
id: TASK-1126
title: "fix(graph): the shell reconcile hook starts overlapping full reindexes"
swimlane: "graph_os"
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-11-24
started: 2026-11-24
completed: 2026-11-24
agent_session: ses-claude-20261123-135444-89e7
depends_on: []
blocked_by: []
references: []
---
# TASK-1126: fix(graph): the shell reconcile hook starts overlapping full reindexes

**Outcome (one sentence):** A Bash command starts at most one full graph reindex at a time, so reindexes no longer pile up and hold the board DB write lock for minutes. A command that only touches scratch paths still reindexes: parsing the command text to skip it was dropped as unsound (docs/playbooks/hook-authoring.md, Anti-patterns).

## Read First
- src/core/hooks/auto-graph-reconcile-shell.sh

## Repro Steps
2026-11-24: commands like 'git clone . $S/clone && cp ... src/...' run in a scratch dir each started cos graph-reindex --force on the main repo; two ran at once (pids 16317 and 38373, parent auto-graph-reconcile-shell.sh) because the 30 s debounce reads the sentinel's age while a reindex takes minutes.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a reindex the hook started is still running, **When** another qualifying command runs, **Then** no second reindex starts.
- **Given** two hooks that both found the sentinel stale, **When** one takes it over first, **Then** the other backs off and only one reindex starts.
- **Given** a reindex the hook started has run past the 15-minute age cap, **When** another qualifying command runs, **Then** it keeps its claim.
- **Given** an rm of a tracked source file in the project, **When** the hook runs, **Then** it still reconciles.

## Work Log
- 2026-11-24 [claude]: commit 020ce11681 — fix(graph): the shell reconcile hook runs one full reindex at a time and none for scratch work
- 2026-11-24 [claude]: commit 6b817be935 — fix(graph): skip a reindex only for provable scratch work, atomically, detached from hook stdio
- 2026-11-24 [claude]: commit 2addb55e9e — fix(graph): every operand counts as a possible path; the reindex job owns its sentinel
- 2026-11-25 [claude]: commit a9b139a9f1 — fix(graph): drop the unsound scratch skip; take a stale reindex sentinel over under a lock
- 2026-11-25 [claude]: commit d5fa398833 — fix(graph): a reindex takeover backs off when the sentinel changed; a long run keeps its claim
- 2026-11-25 [claude]: commit 767974e507 — fix(graph): clearing a crashed reindex lock never removes a fresh one; match the job exactly
- 2026-11-25 [claude]: commit 0416f9b820 — fix(graph): a takeover never removes a sentinel that is already gone; test the 2-hour cap
- 2026-11-25 [claude]: commit e2c24f2c5c — fix(graph): a sentinel gone at the check is never removed; a future mtime counts as stale
- 2026-11-25 [claude]: commit 6247a67cca — refactor(graph): read the reindex sentinel quietly and match the job without a pipe
- 2026-11-25 [claude]: commit c165ae7f53 — fix(graph): a reindex sentinel that is not a regular file is replaced; read it with a size cap
- 2026-11-25 [claude]: commit fb2f4dd179 — fix(graph): a directory at the reindex sentinel path is removed; the job writes its PID by rename
- 2026-11-25 [claude]: commit 1fba3cc39f — docs(playbooks): plain wording for the reindex single-flight anti-pattern
- 2026-11-25 [claude]: commit 44feced8e4 — fix(graph): the reindex job writes its PID through mktemp and a no-follow rename
- 2026-11-25 [claude]: commit 704dd31656 — test(graph): the planted-name test no longer depends on PID order; log an unremovable sentinel
- 2026-11-25 [claude]: commit e78dd606e4 — fix(graph): remove a planted reindex sentinel under the takeover lock; PID 0 or 1 is no job
- 2026-11-25 [claude]: commit 86460c0d0f — fix(graph): a file planted at the reindex lock path no longer blocks every takeover
- 2026-11-25 [claude]: commit 30e50822c2 — fix(graph): an aged plant at the reindex lock path is removed, not only an empty dir
- 2026-11-25 [claude]: commit 5abb15dbb8 — docs(playbooks): an aged plant at the reindex lock path is removed with rm -rf
- 2026-11-25 [claude]: Status transitioned to complete via cos task-done.
