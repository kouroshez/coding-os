---
id: TASK-024
title: "fix health db wrong table names + audit diagnostics for mock data"
swimlane: core
kind: bug
epic: null
labels: [doctor, health, observability]
status: complete
priority: P1
appetite: "2h"
created: 2026-05-23
started: 2026-05-23
completed: 2026-05-23
agent_session: ses-claude-20260523-010526-e647
depends_on: []
blocked_by: []
references:
  - src/core/web/routes/health.py
  - src/core/web/ui/src/pages/DoctorPage.tsx
  - src/core/web/_deps.py
---
# TASK-024: doctor sqlite tab — wrong table names + audit for mocks

**Outcome (one sentence):** Doctor → sqlite tab stops reporting "absent" for tables that exist (just under different names), and every Diagnostics panel is confirmed mock-free.

## Read First
- [src/core/web/routes/health.py](../../src/core/web/routes/health.py) — `_DB_TABLES_OF_INTEREST` (lines 83-94) — checks for `metrics`/`patterns`/`audit_log` which do NOT exist; actual tables are `agent_metrics`/`learned_patterns`/`doc_audit_trail`
- [src/core/web/_deps.py](../../src/core/web/_deps.py) — `make_metrics_dep()` (lines 42-56) — confirms `/api/metrics` data is real Prometheus counters from FastAPI middleware, not mock
- [src/core/web/ui/src/pages/DoctorPage.tsx](../../src/core/web/ui/src/pages/DoctorPage.tsx) — Health & charts tab, Backend tab, SQLite tab

## Repro Steps
1. Open Diagnostics → Doctor → sqlite tab.
2. Observe `metrics: absent`, `patterns: absent`, `audit_log: absent`.
3. `sqlite3 .coding-os/coding-os.db "SELECT name FROM sqlite_master WHERE type='table';"` reveals these never existed under those names — actual names are `agent_metrics` (270 rows), `learned_patterns` (0), `doc_audit_trail` (0).

Expected: tab shows real names + real row counts. Actual: false-negative "absent" labels because the route checks deprecated names.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the Doctor sqlite tab opens
- **When** the user inspects the row-count list
- **Then** `agent_metrics`, `learned_patterns`, `doc_audit_trail` show their real row counts; no false "absent" labels for tables that do exist under canonical names; SPA Health & charts panel carries a one-line caption clarifying the counters are real-time request counts from the SPA's background polling (not mock data); `npm run build` clean.

## Work Log
- 2026-05-23 — fixed `_DB_TABLES_OF_INTEREST` in health.py to use canonical names (`agent_metrics`, `learned_patterns`, `doc_audit_trail`); changed graph root label `.` → `repo-root` in md_links.py + UPDATE on live DB so the canvas shows a recognisable anchor; added Health & charts caption clarifying counters are real Prometheus from FastAPI middleware (numbers move because SPA polls in background); authored docs/_meta/audits/audit-doctor-diagnostics-sweep.md with full 48-self-loop categorization (9 legit + 39 extractor artifacts), mock sweep (only one always-zero placeholder series, no actual mocks), and budget-loading-order documentation (bucket-quota + spine walk, NOT BFS from root). `npm run build` clean.
- 2026-05-23 [claude]: Status transitioned to complete via cos task-done.
