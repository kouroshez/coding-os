---
id: TASK-400
title: "board_os robustness \u2014 allocator error envelope, duplicate-frontmatter enforcement, depends_on format validation"
swimlane: "board_os"
kind: refactor
epic: null
labels: [task-system-review, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-11
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-400: board_os robustness — allocator error envelope, duplicate-frontmatter enforcement, depends_on format validation

**Outcome (one sentence):** cos_task_create returns fail("unavailable") instead of crashing when _allocate_with_prefix exhausts its lock retries; detect_duplicate_frontmatter is actually called in sync_one (currently dead code) and rejects double-YAML task files; _normalize_str_list validates TASK-NNN format for depends_on/blocked_by so malformed ids never reach the cycle detector; cos_task_create's DoR responds honestly (ready=false when block-severity gaps exist, and bug-kind acceptance/repro are fillable in the same call).

## Read First
- src/core/board_os/mcp_tools.py
- src/core/board_os/parser.py
- src/core/board_os/sync.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a DB held locked past the allocator's 8 retries, **When** cos_task_create runs, **Then** it returns fail("unavailable", retryable=true) — never an unhandled OperationalError.
- **Given** a task file with two YAML frontmatter blocks, **When** sync_one parses it, **Then** the sync rejects it loudly (detect_duplicate_frontmatter is wired in, no longer dead code).
- **Given** depends_on: [TASK1, TASK-B-50, garbage], **When** the lean parser normalizes it, **Then** non-TASK-NNN ids are rejected/flagged before reaching the cycle detector.
- **Given** a create whose DoR has block-severity gaps, **When** the envelope returns, **Then** dor.ready is false (today it contradicts itself with ready=true + block gaps).

## Work Log
