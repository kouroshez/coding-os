---
id: TASK-405
title: "System doctor covers graph-backend verdict + extractor stops minting expression-shaped identifier stubs"
swimlane: "graph_os"
kind: bug
epic: null
labels: [graph-os, doctor, hygiene, ready]
status: complete
priority: P1
appetite: 4h
created: 2026-06-12
started: 2026-06-11
completed: 2026-06-11
agent_session: ses-claude-20260611-002926-83d4
depends_on: []
blocked_by: []
references: []
---
# TASK-405: System doctor covers graph-backend verdict + extractor stops minting expression-shaped identifier stubs

---
id: TASK-405
title: "System doctor covers graph-backend verdict + extractor stops minting expression-shaped identifier stubs"
swimlane: "graph_os"
kind: bug
epic: null
labels: [graph-os, doctor, hygiene, ready]
status: icebox
priority: P1
appetite: 4h
created: 2026-06-12
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-405: System doctor covers graph-backend verdict + extractor stops minting expression-shaped identifier stubs

**Outcome (one sentence):** `cos doctor` is whole-system: a new graph.backend_health check surfaces the cos_graph_doctor verdict (healthy flag, real issue categories+counts, fix hint) so Backend-tab problems can never hide from the system doctor; and code_python stops minting identifier stubs whose label is an expression rather than an identifier (spaces/quotes — 956 rows today), with the existing dead-stub GC clearing the legacy rows.

## Read First
- src/cli/doctor_graph.py
- src/core/graph_os/extractors/code_python.py
- src/core/graph_os/tools/graph.py

## Repro Steps
1. Hub Doctor → Backend shows HEALTH=attention (e.g. 17 orphaned phantoms on 2026-06-12) while `cos doctor`'s graph section stays green — the system doctor never consults cos_graph_doctor, so a user running "the doctor" misses backend issues.
2. `SELECT COUNT(*) FROM graph_nodes WHERE kind='identifier' AND (label LIKE '% %' OR label LIKE '%''%')` → 956 stubs whose "identifier" is an over-captured expression (`tasks_dir or project_root_resolved / 'docs' / 'tasks'.resolve`).
Expected: cos doctor reports the backend verdict; identifiers are identifiers. Actual: silent gap + 956 junk rows that re-mint on reindex.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a graph with real doctor issues (e.g. a stale-path node), **When** `cos doctor` runs, **Then** graph.backend_health reports warn/fail with the category counts and the `cos graph-doctor --fix` hint; on a clean graph it reports ok.
- **Given** python source whose call-resolution would previously mint an expression-shaped stub (label containing whitespace/quotes), **When** extracted, **Then** no such identifier stub is emitted (test added) and a full reindex + doctor fix leaves zero expression-shaped stubs.
- **Given** the changes, **When** the graph suite + cli doctor tests run, **Then** green.

## Work Log
- 2026-06-12 [claude]: Edit doctor_graph.py
- 2026-06-12 [claude]: Edit code_python.py
- 2026-06-12 [claude]: Edit code_python.py
- 2026-06-12 [claude]: Edit code_python.py
- 2026-06-12 [claude]: Edit code_python.py
- 2026-06-12 [claude]: cos doctor gained graph.backend_health — surfaces the cos_graph_doctor verdict (healthy / real-category counts / fix hin
- 2026-06-12 [claude]: Status transitioned to complete via cos task-done.
