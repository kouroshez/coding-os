---
id: TASK-086
title: "Hub UI: Metrics tab — thinking_os counters, task velocity, dispatch hit-rate dashboard"
swimlane: core
kind: feature
epic: hub-tab-scaffold
labels: [hub, ui, metrics, telemetry]
status: icebox
priority: P3
appetite: "5h"
created: 2026-04-24
started: null
completed: null
agent_session: null
depends_on: [TASK-072]
blocked_by: []
references: []
---

# TASK-086: Hub UI — Metrics tab

**Outcome (one sentence):** Operators open `/metrics` in the Hub and see a small dashboard combining (a) the raw Prometheus text scrape from `/metrics` (already served by `core/web/routes/metrics.py`) and (b) derived charts: task throughput, pattern promotions, router-layer hit rates, retrieval precision — all pulled from `thinking_os.db::metrics` without requiring an external Grafana.

## Read First

- [core/web/routes/metrics.py](../../core/web/routes/metrics.py) — existing `/metrics` endpoint (Prometheus text format).
- [core/graph_os/enterprise.py](../../core/graph_os/enterprise.py) — `metrics()` / `.render()` source of the counters exposed at `/metrics`.
- [core/thinking_os/tools/metrics.py](../../core/thinking_os/tools/metrics.py) — MCP tool surface for per-task and router metrics.
- [core/thinking_os/db.py](../../core/thinking_os/db.py) — `metrics` table schema (search for `CREATE TABLE metrics`).
- [docs/engineering/hub-architecture.md](../../docs/engineering/hub-architecture.md) — tab contract.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** the Metrics tab is opened
  **When** it renders
  **Then** four cards show: **Task Throughput** (line chart — tasks/day over 30d, from `task_status_history`), **Pattern Promotions** (counter with sparkline from `cos_learn_*` events), **Router Layer Hit-Rate** (stacked bar: memory / docs / tasks / graph / code-grep for last 7d), **Retrieval Precision** (gauge 0–100% from retrieval feedback — TASK-087 feeds into this).
- **Given** the raw metrics endpoint
  **When** the user clicks "Show raw scrape"
  **Then** the right side-panel mounts a read-only text view of the Prometheus exposition exactly as `/metrics` returns — useful for debugging.
- **Given** a 30-day window with no data in some bins
  **When** the chart renders
  **Then** missing bins are drawn as zeros (not gaps), and the axis labels the UTC day — no timezone surprise.
- **Given** a metric surface that grows (new `cos_*` tool counter added)
  **When** the tab reloads
  **Then** the new metric appears in the raw scrape without a UI change; specific cards are opt-in derivations so they gracefully show "no data" when the underlying counter isn't wired yet.
- **Tests:** `tests/test_metrics_dashboard_endpoint.py` asserts JSON shape for each card; Playwright `e2e/metrics-dashboard.spec.ts` covers render + empty-state.

## Implementation Notes

1. **Backend aggregations:** add `GET /api/p/<slug>/metrics/dashboard?window=30d` returning `{cards: [...], as_of: ts}`. Internally runs small SQLite queries:
   - Throughput: `SELECT date(transitioned_at), count(*) FROM task_status_history WHERE new_status='complete' GROUP BY 1`.
   - Router hit-rate: `SELECT layer, count(*) FROM retrieval_router_log WHERE ts > now-7d GROUP BY layer` (reuse TASK-018 append-only log).
   - Retrieval precision: `AVG(feedback_value)` from TASK-087's table when it exists; otherwise return `null` and the gauge shows empty.
2. **UI:** `features/metrics/MetricsPage.tsx` + small chart components built on `recharts` (already a dep if present; otherwise minimal inline SVG — no heavy new deps).
3. **Refresh:** dashboard auto-refreshes every 60 s; manual refresh button shows last-fetched age.
4. **No retention policy change** in this task — if retention is missing, file a follow-up. We only *read* existing tables.
5. Tab feature-flagged by `hub-config.json::metrics.enabled`.
6. Do not log PII: agent names are fine, raw query text is NOT displayed — stripped by the backend before surfacing.

## Dependencies

- **Depends on:** TASK-072 (feature flag).
- **Soft-deps:** TASK-087 (Retrieval Feedback) — the precision gauge stays empty until feedback data exists, but the tab ships standalone.

## Work Log
