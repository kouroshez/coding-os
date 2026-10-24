---
id: TASK-1070
title: "fix(hooks): verify ledger records PASS for a suite whose failure a pipe or ; hid"
swimlane: core
kind: bug
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
# TASK-1070: fix(hooks): verify ledger records PASS for a suite whose failure a pipe or ; hid

**Outcome (one sentence):** record-verify-auto records PASS only when the suite's own exit status is the command's exit status; a command that can mask it (pipe, ;, ||, background &) records nothing on success, so a red suite can never become a ledger-green that test-governor then refuses to re-run.

## Read First
- docs/engineering/test-governance.md

## Repro Steps
1. Session 2026-10-24: `make verify-hooks 2>&1 | tail -4; uv run ruff check …` — make exited 1 (SC2034), ruff passed, Bash exit 0.
2. Next `make verify-hooks` → test-governor: "BLOCKED: verify-hooks is already green on this exact tree".
3. Source: record-verify-auto.sh maps PostToolUse (whole-command success) to suite PASS.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `make verify-hooks 2>&1 | tail -4; uv run ruff check x` that exits 0 while make failed **When** record-verify-auto runs **Then** no PASS is recorded for verify-hooks
- **Given** a plain `make verify-hooks` or an `&&` chain that exits 0 **When** it runs **Then** PASS is recorded as before
- **Given** `2>&1` redirections **When** the command is classified **Then** they do not count as masking

## Work Log
- 2026-10-24 [claude]: Status transitioned to complete via cos task-done.
