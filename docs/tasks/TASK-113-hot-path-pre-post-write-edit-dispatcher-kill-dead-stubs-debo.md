---
id: TASK-113
title: "Hot-path Pre/Post Write|Edit dispatcher + kill dead stubs + debounce test-first + fix auto-regen-doc-index dead path"
swimlane: core
kind: refactor
epic: hook-remediation
labels: [hooks, performance, dispatcher, audit-n9, ready]
status: complete
priority: P2
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-113: Hot-path Pre/Post Write|Edit dispatcher + kill dead stubs + debounce test-first + fix auto-regen-doc-index dead path

**Outcome (one sentence):** The dominant per-edit/per-session hook costs are eliminated via safe single-hook fixes — test-first-reminder + warn-mcp-down debounced, auto-regen-doc-index dead path fixed, auto-brain-decay marker aligned — while the registry/golden-heavy dispatcher refactor + dead-stub removal + memory-check auto-stamp are refiled (TASK-161) for a clean no-concurrent-session window.

## Read First
- src/core/hooks/test-first-reminder.sh
- src/core/hooks/warn-mcp-down.sh
- src/core/hooks/auto-regen-doc-index.sh

## Repro Steps
1. test-first-reminder runs a `find -maxdepth 6` over ~6k files on every edit of the same file (no debounce).
2. warn-mcp-down spawns the full MCP server for a handshake on every SessionStart — including each compact/resume of a long session.
3. auto-regen-doc-index's candidate paths miss src/scripts/regen_doc_index.py from a symlinked install → silent no-op.
Expected: each runs at most once per session/file; doc-index finds its script.
Actual: repeated heavy scans + a dead doc-index hook.

## Acceptance (G/W/T)
- **Given** repeated edits of one file, **When** test-first-reminder fires, **Then** it reminds at most once per file per session (panel marker, cleared each SessionStart).
- **Given** a compact/resume within COS_MCP_PROBE_TTL, **When** warn-mcp-down fires, **Then** it skips the spawn-probe.
- **Given** a doc edit, **When** auto-regen-doc-index runs, **Then** it resolves src/scripts/regen_doc_index.py.
- **Given** the dispatcher refactor (9a) + dead-stub removal (9b) + memory-check auto-stamp, **When** scoped, **Then** they are refiled as TASK-161 (registry+golden-heavy, clean-window only).

## Work Log
- 2026-06-05 [claude]: 9c test-first-reminder debounced per-file-per-session (panel marker, cleared on SessionStart); 9d auto-regen-doc-index f
