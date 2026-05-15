---
id: TASK-001
title: "fix(doctor): ID collision + broken symlink crash + new health checks C45-C48"
swimlane: cli
kind: bug
epic: null
labels: []
status: complete
priority: P2
appetite: "1d"
created: 2026-05-15
started: 2026-05-14
completed: 2026-05-14
agent_session: ses-claude-20260514-212614-447e
depends_on: []
blocked_by: []
references: []
---
# TASK-001: fix(doctor): ID collision + broken symlink crash + new health checks C45-C48

**Outcome (one sentence):** `cos doctor` output has unique check IDs, never crashes on broken hook symlinks, and surfaces 4 previously invisible health signals (agent identity, adapter dir symlinks, consumer project hooks, Rule-3 compliance).

## Read First
- src/cli/doctor.py — C7 adapter check, run_doctor orchestration
- src/cli/doctor_board.py — board checks currently using colliding IDs C24-C27
- src/cli/doctor_graph.py — C19 WARN without remediation hint
- src/cli/doctor_extras.py — run_extra_checks entry point

## Repro Steps
1. Run `cos doctor` and observe C24 appears twice (graph + board)
2. Create a broken symlink in .claude/hooks/ → `cos doctor` crashes in C7 (`stat()` on broken symlink)
3. `cos doctor` shows C19 WARN with no fix command
Expected: unique IDs, no crash, actionable WARNs, 4 new checks
Actual: ID collision, potential crash, silent WARN, gaps in coverage

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `cos doctor` runs on this meta-repo
- **When** all checks complete
- **Then** no check ID appears more than once, board uses C50-C53, C19 WARN includes `cos graph-reindex`, C45-C48 all appear and pass

## Work Log
- 2026-05-15: fixed board ID collision (C50-C53), C19 remediation hint, C7 symlink crash, added C45-C48 checks; 49 CLI tests pass
- 2026-05-15 [claude]: Status transitioned to complete via cos task-done.
