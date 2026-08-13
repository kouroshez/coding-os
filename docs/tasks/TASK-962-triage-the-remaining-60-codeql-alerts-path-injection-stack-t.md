---
id: TASK-962
title: "Triage the remaining 60 CodeQL alerts: path-injection, stack-trace-exposure, clear-text-storage"
swimlane: core
kind: chore
epic: null
labels: [codeql, hub, ready]
status: in_progress
priority: P2
appetite: 2d
created: 2026-08-13
started: 2026-08-13
completed: null
agent_session: ses-claude-20260812-170221-1654
depends_on: []
blocked_by: []
references: []
---
# TASK-962: Triage the remaining 60 CodeQL alerts: path-injection, stack-trace-exposure, clear-text-storage

**Outcome (one sentence):** The three CodeQL classes left after TASK-961 are each either fixed or dismissed with recorded evidence. 27x py/path-injection (Hub routes reading files from request-supplied paths) get one shared containment helper rather than 27 ad-hoc guards; 19x py/stack-trace-exposure collapse to ~8 real leak sites where str(exc) reaches a response body — the other 11 are shared helpers the taint passes through, so patching them would suppress the alert without fixing the leak; 6x py/clear-text-storage in agent_memory_sync.py and its golden copies, 1x py/clear-text-logging in session_startup.py, and 2x py/bad-tag-filter in graph_os tests are assessed individually.

## Work Log
- 2026-08-13 [claude]: Edit _bounded_read.py
- 2026-08-13 [claude]: Edit _config_shared.py
- 2026-08-13 [claude]: Edit _envelope.py
- 2026-08-13 [claude]: commit 41946cf92f — fix(graph_os): use SHA-256 for the three derived content digests
- 2026-08-13 [claude]: commit cf343c3ec5 — fix(security): one path-segment validator, applied where request data joins a path
- 2026-08-13 [claude]: commit 7fbffcb530 — fix(security): log exceptions under a correlation id instead of returning str(exc)
- 2026-08-13 [claude]: Edit ci-gates.md
- 2026-08-13 [claude]: commit ad6b4d9ce4 — docs(ci-gates): record the CodeQL fix-vs-dismiss policy and the reachability test
- 2026-08-13 [claude]: Edit test_route_path_traversal.py
- 2026-08-13 [claude]: Edit test_route_path_traversal.py
- 2026-08-13 [claude]: commit 22212bed15 — test: prove the path-traversal guards block a real file above the root
- 2026-08-13 [claude]: All 59 real CodeQL findings resolved: 3 weak-hash to SHA-256 (usedforsecurity=False did NOT satisfy the query - it…
- 2026-08-13 [claude]: commit c8dec8eff3 — fix(ci): drop the unused noqa that failed the ruff gate
