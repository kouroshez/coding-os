---
id: TASK-310
title: "Repair TASK-116 duplicate YAML frontmatter (conflicting status) + task-validate guard for dup frontmatter blocks"
swimlane: "board_os"
kind: bug
epic: null
labels: [ready, data-integrity, audit-2026-06-09]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-10
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-310: Repair TASK-116 duplicate YAML frontmatter (conflicting status) + task-validate guard for dup frontmatter blocks

**Outcome (one sentence):** TASK-116's file carries exactly one frontmatter block with its true status (icebox), and `cos task-validate` FAILS loudly on any task file containing two YAML frontmatter blocks so this corruption class can never silently skew board counts again.

## Read First
- docs/tasks/TASK-116-b0-agent-memory-thinking-os-tool-name-drift-fix-skill-code-dri.md (the corrupted file: block 1 says complete, block 2 says icebox)
- src/core/board_os/parser.py (frontmatter parse — currently takes first block silently)
- src/cli/board.py (task-validate implementation)

## Repro Steps
1. Open TASK-116 file → two `---` fenced YAML blocks, statuses `complete` vs `icebox`.
2. Run `cos task-validate`.
Expected: validation error naming the file and the conflict.
Actual: passes silently; board sees `complete` while intended state is `icebox` (true open-task count is wrong).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a task file containing two YAML frontmatter blocks
- **When** `cos task-validate` runs
- **Then** it exits non-zero and reports the file + conflicting statuses, with a board_os regression test
- **Given** the repaired TASK-116
- **When** `cos task-show TASK-116` runs
- **Then** it shows a single status `icebox` and the file has exactly one frontmatter block (repair via semantic ops / parser-aware fixer, not a status hand-edit)

## Work Log
