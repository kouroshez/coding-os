---
id: TASK-523
title: "Harden cos pr executor: reaper fail-safe + reap lock, session collision, breaker order/scope, heal-budget reset, subprocess timeouts"
swimlane: core
kind: bug
epic: multi-agent-pr-mode
labels: [pr-mode, pr-mode-hardening, cli, concurrency, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-22
started: 2026-06-22
completed: 2026-06-23
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-523: Harden cos pr executor: reaper fail-safe + reap lock, session collision, breaker order/scope, heal-budget reset, subprocess timeouts

> **Re-materialized 2026-06-24 (TASK-532).** Reconstructed from the board DB metadata + the shipping commit `72955752`. The original body was never persisted (the task closed without a file ever written → `body` is null in the DB and the file never existed in git), so Outcome / Read First / Acceptance below are faithfully reconstructed from the title and the committed diff; the Work Log records the real commit.

**Outcome (one sentence):** The `cos pr` executor is hardened against the `/code-review ultra` findings — the reaper reaps only on positive offline evidence (no live-worktree data-loss) and is flock-serialized, the per-session open-PR cap is checked before any push, the heal budget resets on cleanup/reap, every gh/git subprocess call is timeout-bounded, and `_agent_session` is unique-per-process (no shared "nosession" collision).

## Read First
- src/cli/pr_commands.py
- docs/playbooks/pr-workflow.md

## Repro Steps
Drive the pr-mode loop with concurrent sessions on one consumer repo: a presence-offline pill (idle >30min) caused the reaper to GC a live worktree; a same-instant reap double-removed; the open-PR cap was checked after the push (orphaning a pushed branch); a stalled gh/git call wedged the agent's turn loop.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a presence-offline session whose worktree may hold uncommitted work **When** the reaper runs **Then** it does not remove a live owner's worktree (positive death evidence only).
- **Given** two reapers racing **When** they sweep **Then** a flock serializes them (no double-remove / ledger churn).
- **Given** the per-session open-PR cap is reached **When** submit runs **Then** it refuses BEFORE pushing (no orphaned branch).
- **Given** any gh/git call **When** the network stalls **Then** the call is timeout-bounded and the loop stays non-blocking.
- **And** `uv run pytest tests/test_cli.py -q` is green.

## Work Log
- 2026-06-23 [claude]: Shipped in commit 72955752 — reaper fail-safe + reap lock, session-id collision fix, breaker order/scope, heal-budget reset, subprocess timeouts.
- 2026-06-24 [claude]: File re-materialized from DB metadata (TASK-532); original body unrecoverable (never persisted to disk / git).
- 2026-06-24 [claude]: committed d8d81744 · 3 files
