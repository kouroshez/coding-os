---
id: TASK-924
title: "refactor: split src/cli/main.py (3111 lines) into cohesive command and scaffold modules"
swimlane: cli
kind: refactor
epic: null
labels: [tech-debt, cli, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-10
started: 2026-08-11
completed: 2026-08-11
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-924: refactor: split src/cli/main.py (3111 lines) into cohesive command and scaffold modules

**Outcome (one sentence):** src/cli/main.py drops under the 500-line backstop by moving each independently changeable concern — the scaffold phase engine, the overlay/boundary machinery, the dry-run previews, the interactive world builder, and the standalone commands — into siblings, with the cos CLI surface (every command, flag and help string) unchanged.

## Read First
- docs/architecture/raptor-consolidation.md
- src/cli/main.py
- src/core/rules/anti-overengineering.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the split has landed **When** `uv run pytest tests/test_cli.py -q` runs **Then** it passes with no test edits beyond import paths.
**Given** a user runs `cos --help` and `cos init --help` **When** the output is compared to before the split **Then** the command list, flags and help text are identical.
**Given** the file-size scanner runs **When** it reports on src/cli **Then** main.py is no longer listed as an error-tier violation.

## Work Log
- 2026-08-11 [claude]: Status transitioned to complete via cos task-done.
