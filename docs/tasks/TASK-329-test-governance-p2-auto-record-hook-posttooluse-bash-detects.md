---
id: TASK-329
title: "Test-governance P2: auto-record hook \u2014 PostToolUse Bash detects suite commands, records PASS/FAIL to ledger"
swimlane: core
kind: feature
epic: test-governance
labels: [test-governance, hooks, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-10
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260527-151803-0b9f
depends_on: [TASK-328]
blocked_by: []
references: []
---
# TASK-329: Test-governance P2: auto-record hook — PostToolUse Bash detects suite commands, records PASS/FAIL to ledger

**Outcome (one sentence):** New registry.yaml-registered PostToolUse Bash hook matches completed verify-suite commands (data-driven from verify-suites.yaml, no hardcoded paths) and records result + commit keys via record-verify.sh; fail-open; flock-serialized.

## Read First
- docs/engineering/test-governance.md
- src/core/hooks/registry.yaml
- src/core/board_os/verify-suites.yaml
- src/core/hooks/record-verify.sh
- src/core/skills/hook-authoring/SKILL.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a matrix suite command finishing with exit 0 or 1
- **When** the hook fires (synthetic JSON payload test)
- **Then** .last-verify.json gains the suite entry with status+git_head+agent; malformed input exits 0; make verify-hooks + pytest hook test green

## Work Log
- 2026-06-10 [claude]: Status transitioned to complete via cos task-done.
