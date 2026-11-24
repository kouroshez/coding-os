---
id: TASK-1100
title: "fix(cli): cos update never calls an older published version newer"
swimlane: cli
kind: bug
epic: null
labels: [cli, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-11-24
started: 2026-11-23
completed: 2026-11-23
agent_session: ses-claude-20261123-135444-89e7
depends_on: []
blocked_by: []
references: []
---
# TASK-1100: fix(cli): cos update never calls an older published version newer

**Outcome (one sentence):** cos update prints the upgrade notice only when the published coding-os is strictly newer than the installed one.

## Read First
- src/cli/update.py
- src/cli/core_version.py
- tests/test_core_version_release_check.py
- docs/governance/release-process.md

## Repro Steps
After the 0.4.2 release, cos update --dry-run in streamos printed "A newer coding-os is published: 0.4.1 (installed 0.4.2)": _release_notice in src/cli/update.py tests latest != installed, and the PyPI JSON API served a cached 0.4.1 for minutes after upload.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** cos 0.4.2 installed from the checkout and the PyPI JSON still reporting 0.4.1, **When** cos update runs, **Then** no "newer coding-os is published" line is printed.
- **Given** PyPI reports 0.9.0 and 0.3.12 is installed, **When** cos update runs, **Then** the notice names 0.9.0 and the upgrade command as before.

## Work Log
- 2026-11-24 [claude]: Status transitioned to complete via cos task-done.
