---
id: TASK-263
title: "Log feed fragments by CWD \u2014 state_dir must anchor to project root, not cwd"
swimlane: core
kind: bug
epic: hub-redesign
labels: [logging, hub, observability, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-20260608-021813-db02
depends_on: []
blocked_by: []
references: []
---
# TASK-263: Log feed fragments by CWD — state_dir must anchor to project root, not cwd

**Outcome (one sentence):** `logging_os.config.state_dir()` falls back to a CWD-relative `.coding-os` when `COS_STATE_DIR` is unset, so processes with different CWDs write logs to different `.coding-os/.cos.log.jsonl` files and the Hub Logs panel (rooted at the repo) misses the MCP server's feed; anchor it to the discovered project root.

## Read First
- src/core/logging_os/config.py (state_dir / text_log_path / db_path)
- src/core/web/routes/logs.py (_jsonl_log_path reads `<project_root>/.coding-os/.cos.log.jsonl`)

## Repro Steps
1. `find . -name .cos.log.jsonl -not -path '*/node_modules/*'` → 3 files (root, src/core, src/core/thinking_os), each freshly written.
2. Open the Hub Logs panel (reads the root file) while agents work → sparse feed; the MCP server's `py.thinking_os` activity lands in `src/core/thinking_os/.coding-os/.cos.log.jsonl` instead.
Expected: one log sink the panel fully sees.
Actual: logs fragment by process CWD; panel under-reports.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `COS_STATE_DIR` unset and a process whose CWD is a subdirectory of the repo,
- **When** `state_dir()` resolves the `.coding-os` path,
- **Then** it returns `<project-root>/.coding-os` (walked up for `.git`/`pyproject.toml`), so every process single-sinks to one log file; `COS_STATE_DIR`/`COS_DB_PATH`/`COS_LOG_FILE` still win; no project marker → CWD fallback unchanged; a unit test pins all three cases.

## Work Log
- 2026-06-08 [claude]: Fixed (007df5d1): logging_os.config.state_dir() now anchors .coding-os to the project root via _discover_project_root() 
