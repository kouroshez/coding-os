---
id: TASK-347
title: "cos doctor --bootstrap \u2014 preflight prerequisite checks (python/bash/git/uv/sed)"
swimlane: cli
kind: feature
epic: A-install
labels: [wave-0, onboarding-program, ready]
status: archive
priority: P0
appetite: 1d
created: 2026-06-11
started: 2026-06-10
completed: 2026-06-10
agent_session: ses-claude-20260610-185418-2b3f
depends_on: []
blocked_by: []
references: []
---
# TASK-347: cos doctor --bootstrap — preflight prerequisite checks (python/bash/git/uv/sed)

**Outcome (one sentence):** `cos doctor --bootstrap` validates python>=3.10, bash>=4, git, uv presence and BSD/GNU sed compatibility with per-check pass/fail + fix hints; README quickstart and `cos init` reference it; non-TTY safe.

## Read First
- src/cli/doctor.py
- README.md
- src/adapters/claude/install.sh
- src/core/scripts/install-adapter.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a machine with bash 3.2 (macOS default), **When** `cos doctor --bootstrap` runs, **Then** the bash check fails with the exact `brew install bash` hint while other checks still report.
- **Given** all prerequisites satisfied, **When** the command runs, **Then** every check prints PASS and exit code is 0; any failure → non-zero exit with only failing checks summarized.
- **Given** a CI/non-TTY environment, **When** the command runs, **Then** output is plain text with no prompts and tests in tests/test_cli.py cover pass/fail/sed-flavor paths.

## Work Log
- 2026-06-11 [claude]: Shipped --bootstrap probe-and-exit mode (commit 7a501d89): 5 bootstrap.* checks (python>=3.10, bash>=4 w/ brew hint, git
