---
id: TASK-530
title: "cos pr cleanup force-deletes worktree/branch with no merge check \u2014 gate on confirmed-merged unless --force"
swimlane: infra
kind: bug
epic: pr-mode-hardening
labels: [pr-mode, data-loss, cleanup, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-23
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-530: cos pr cleanup force-deletes worktree/branch with no merge check — gate on confirmed-merged unless --force

**Outcome (one sentence):** cos pr cleanup refuses to remove the worktree + local branch unless the PR is confirmed merged (or closed), with an explicit --force escape hatch for the human — so an agent driving the documented loop linearly cannot destroy local unmerged work when CI is still running or red.

## Read First
- src/cli/pr_commands.py
- docs/playbooks/pr-workflow.md

## Repro Steps
In a pr-mode worktree run `cos pr open` → edit → `cos pr submit` (PR opens, CI pending) → immediately `cos pr cleanup` → worktree remove --force + branch -D run with no merge check; if the push hadn't landed the local commits are gone.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an unmerged/open PR for the branch **When** `cos pr cleanup` runs without --force **Then** it refuses and keeps the worktree+branch, naming the PR state.
- **Given** a merged PR **When** cleanup runs **Then** it removes the worktree + local branch + prunes.
- **Given** --force **When** cleanup runs **Then** it removes regardless (human override).
- **And** `uv run pytest tests/test_cli.py -q` is green.

## Work Log
