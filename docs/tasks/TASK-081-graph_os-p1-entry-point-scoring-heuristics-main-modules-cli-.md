---
id: TASK-081
title: "graph_os P1: Entry-point scoring heuristics (main modules, CLI commands, HTTP routes, cron jobs, test fixtures)"
swimlane: graph_os
kind: feature
epic: graph_os-graph-tool-parity
labels: [hub, graph, entry-points, P1-parity]
status: icebox
priority: P1
appetite: "4h"
created: 2026-04-24
started: null
completed: null
agent_session: null
depends_on: [TASK-080]
blocked_by: []
references: []
---

# TASK-081: graph_os P1 — Entry-point scoring heuristics

**Outcome (one sentence):** `cos_graph_trace` picks high-scoring entry points by default, and the Hub Graph tab gets a "Start from entry point" quick-action list sorted by score; every entry point carries a provenance tag (`main`, `cli`, `http`, `cron`, `test`, `script`).

## Read First

- [core/graph_os/extractors/contracts.py](../../core/graph_os/extractors/contracts.py) — framework detection (fastapi/drf/flask/django/celery) already identifies route handlers; extend rather than duplicate.
- [core/graph_os/tools/graph_trace.py](../../core/graph_os/tools/) — where the default "start node" is chosen today (currently naive degree-heuristic).
- [cli/main.py](../../cli/main.py) — `click` entry pattern is itself an entry-point source.
- [core/graph_os/types.py](../../core/graph_os/types.py) — `NodeKind` enum; we add an `entry_kind: str | None` attribute, not a new NodeKind.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** a polyglot repo with: a `__main__.py`, a `click` CLI group, a FastAPI router, a Celery `@task`, and a `pytest` fixture
  **When** `cos graph-entrypoints --top 20` runs
  **Then** output lists all five kinds of entry points, each with a numeric score in `[0.0, 1.0]`, a stable `entry_kind` tag, and the file path + line.
- **Given** the Hub Graph tab with data loaded
  **When** the user opens the right panel
  **Then** a "Start from entry point" list appears at the top with the top-10 entry points for the currently selected language filter.
- **Given** `cos_graph_trace("user_login_flow")` called by an MCP client without an explicit `start_node`
  **When** the call resolves
  **Then** the starting node is the highest-scoring entry point whose semantic signature contains "login", and the returned trace includes that choice in `metadata.start_source = "entry-point-heuristic"`.
- **Tests:** `core/graph_os/tests/test_entrypoints.py` with one golden fixture per entry-kind (≥ 8 assertions); the Hub UI Playwright suite asserts the quick-action list renders for a fresh index.

## Scoring heuristic (deterministic, no ML)

```
score = 0.0
+ 0.3   if node matches main-pattern       (__main__, func main, public static void main, fn main)
+ 0.3   if node is a registered CLI command (click, typer, cobra, clap)
+ 0.3   if node is a registered HTTP route   (fastapi, flask, drf, gin, express)
+ 0.2   if node is a scheduled job           (celery.task, rq, apscheduler, k8s CronJob)
+ 0.2   if node is a test fixture            (@pytest.fixture, Go TestMain, rust #[test])
+ 0.1   if node is reachable from the module top-level (not inside a nested class)
+ 0.1   per unique inbound CALLS edge       (capped at +0.3)
- 0.2   if node name starts with "_" or "test_" and entry_kind != "test"
```

Final score clipped to `[0.0, 1.0]`, stored on the node as `entry_score`.

## Implementation Notes

1. Extend `contracts.py` with 5 new detectors: `detect_main`, `detect_cli`, `detect_http_route`, `detect_cron`, `detect_test_fixture`. Each returns `(NodeID, entry_kind)`.
2. New single-pass file `core/graph_os/entry_points.py` runs after all extractors, reads the `entry_kind` attributes, and computes `entry_score` using the formula above.
3. Expose via `cos_graph_entrypoints` MCP tool + CLI `cos graph-entrypoints`.
4. `cos_graph_trace` consults `entry_score` when no explicit start is given.
5. Hub UI: new panel `EntrypointList.tsx` under `features/graph/` — reads `/api/p/<slug>/graph/entrypoints`.

## Dependencies

- **Depends on:** TASK-080 (need tree-sitter to detect `main()` robustly across languages).
- **Unblocks:** TASK-075 (process-grouped search uses entry points as process anchors).

## Work Log
