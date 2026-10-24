---
id: TASK-1072
title: "Remove the nightly maintenance pipeline and age-based task auto-archive"
swimlane: infra
kind: refactor
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-10-24
started: 2026-10-24
completed: 2026-10-24
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1072: Remove the nightly maintenance pipeline and age-based task auto-archive

**Outcome (one sentence):** No scheduled job runs on any machine: src/core/scheduled/, cos cron, cos-nightly, the launchd/systemd templates, the /api/scheduled routes, the Hub Scheduled Maintenance panel, the doctor schedule check and the Makefile cron targets are gone, and tasks are never archived by age.

## Read First
- docs/engineering/scheduled-jobs.md
- docs/governance/task-lifecycle.md
- src/core/board_os/_mcp_stranded.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a fresh checkout, **When** I search src/ tests/ Makefile pyproject.toml for the nightly pipeline, **Then** nothing references it.
- **Given** cos doctor runs, **When** it finishes, **Then** no scheduled.cron_configured check appears and nothing fails for a missing cron.
- **Given** a complete task older than 30 days, **When** cos daily or a session start runs, **Then** its status stays complete.
- **Given** the Hub Settings page, **When** it renders, **Then** no Scheduled Maintenance section is shown and the UI build and tests pass.

## Work Log
- 2026-10-24 [claude]: Removed src/core/scheduled (12 legs, launchd/systemd), cos cron, cos-nightly, /api/scheduled + Hub panels, doctor…
- 2026-10-24 [claude]: Verify: make verify-hooks clean; test_hooks_fail_closed + test_template_scaffold_* 112 passed/1 skipped (workspace…
