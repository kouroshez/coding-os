---
id: TASK-527
title: "pr-mode autonomy deadlocks on a no-required-check repo \u2014 submit opens a PR that never auto-merges"
swimlane: infra
kind: bug
epic: pr-mode-hardening
labels: [pr-mode, autonomy, auto-merge, critical, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-23
started: 2026-06-23
completed: 2026-06-23
agent_session: ses-claude-20260623-175054-847a
depends_on: []
blocked_by: []
references: []
---
# TASK-527: pr-mode autonomy deadlocks on a no-required-check repo — submit opens a PR that never auto-merges

**Outcome (one sentence):** A fresh consumer with a remote + gh but no branch-protection/required-status-check never silently strands a PR — `cos pr submit` either falls back to an explicit `gh pr merge --squash` after the agent's own validate passed, or emits a clear degraded status naming the missing required-check; behavior is governed by the autonomy_level setting (TASK-533).

## Read First
- src/cli/pr_commands.py
- docs/playbooks/pr-workflow.md

## Repro Steps
With a real remote + authenticated gh and NO ruleset/required check, run `cos pr submit` → a PR is created, `auto_merge_armed=False`, and nothing further happens; the PR stays open forever (the user's use case (i): main-only).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** remote+gh and NO required check **When** `cos pr submit` runs **Then** the PR is either merged via an explicit fallback OR submit emits an explicit degraded status naming the missing required-check (never a silent open PR).
- **Given** a required check exists **When** submit runs **Then** auto-merge is armed exactly once (test asserts `gh pr merge --auto --squash`).
- **And** `uv run pytest tests/test_cli.py -q` is green.

## Work Log
- 2026-06-24 [claude]: Edit pr-workflow.md
- 2026-06-24 [claude]: Deliberation: fix the SILENT deadlock minimally — submit now emits an explicit merge_status (auto-merge-armed |…
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit test_cli.py
- 2026-06-24 [claude]: commit ed745e1d5d — fix(pr-mode): submit surfaces explicit merge_status, no silent PR strand on no-required-check repo
- 2026-06-24 [claude]: Status transitioned to complete via cos task-done.
