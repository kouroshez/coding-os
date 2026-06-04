---
id: TASK-068
title: "cos graph-reindex: live progress bar over files (sequential + parallel paths)"
swimlane: infra
kind: feature
epic: null
labels: [graph_os, cli, ux]
status: in_progress
priority: P3
appetite: "2h"
created: 2026-06-04
started: 2026-06-03
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-068: cos graph-reindex: live progress bar over files (sequential + parallel paths)

**Outcome (one sentence):** cos graph-reindex shows a click.progressbar advancing per file (both the sequential and ProcessPoolExecutor parallel paths), auto-hidden on non-TTY (CI/pipes) so summary-only output is unchanged there. Replaces the per-file cache-hit echo spam; errors + final summary still print.

## Read First
- src/cli/graph_commands.py
- docs/engineering/graph_os-queries.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a TTY terminal, **When** `cos graph-reindex [--force] [--workers N]` runs, **Then** a progress bar advances once per file (both sequential and parallel paths) and the final `processed/skipped/errors/duration` summary still prints.
- **Given** a non-TTY stdout (pipe/CI), **When** the same command runs, **Then** the bar is auto-hidden (click.progressbar behaviour) and only the summary + any error lines print.
- **Given** the change, **When** `uv run pytest tests/test_cli.py -q` runs, **Then** it is green.

## Work Log
