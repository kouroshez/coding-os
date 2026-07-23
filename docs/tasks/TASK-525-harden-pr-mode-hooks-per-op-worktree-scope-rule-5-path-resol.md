---
id: TASK-525
title: "Harden pr-mode hooks: per-op worktree scope + Rule-5 path resolve in branch-guard & block-shared-tree-edit, push-target forms"
swimlane: core
kind: bug
epic: multi-agent-pr-mode
labels: [pr-mode, pr-mode-hardening, hooks, ready]
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
# TASK-525: Harden pr-mode hooks: per-op worktree scope + Rule-5 path resolve in branch-guard & block-shared-tree-edit, push-target forms

> **Re-materialized 2026-06-24 (TASK-532).** Reconstructed from the board DB metadata + the shipping commit `74178b82`. The original body was never persisted (the task closed without a file ever written → `body` is null in the DB and the file never existed in git), so Outcome / Read First / Acceptance below are faithfully reconstructed from the title and the committed diff; the Work Log records the real commit.

**Outcome (one sentence):** pr-mode hook scope is decided PER git-op via `_git_dir_target` (honors `-C`, closing the `cd <wt> && git -C <main> reset` bypass), `_is_worktree_path` + `block-shared-tree-edit` `FILE_ABS` are realpath-resolved (Rule 5: macOS /tmp ↔ /private/tmp), and the push guard covers the `--mirror` / `--all` / `+main` forms.

## Read First
- src/core/hooks/_helpers/branch_guard_check.py
- src/core/hooks/block-shared-tree-edit.sh

## Repro Steps
In pr-mode: `cd <worktree> && git -C <main-repo> reset HEAD~1` was treated as worktree-scoped (command-global scope) and allowed a HEAD-rewrite on the shared integration checkout; an unresolved /tmp vs /private/tmp path mismatch let a shared-tree edit slip; and `git push --mirror` / `+main` bypassed the protected-branch push guard.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `cd <wt> && git -C <main> reset HEAD~1` in pr-mode **When** branch-guard evaluates it **Then** scope is judged per-op from `-C` (the main checkout) → BLOCK.
- **Given** a worktree path under /tmp (symlinked to /private/tmp) **When** the guard compares it **Then** both sides are realpath-resolved (Rule 5) so the compare holds.
- **Given** `git push --mirror` / `--all` / `+main` **When** the push guard runs **Then** the protected/integration branch is still blocked.
- **And** `make verify-hooks` + `uv run pytest tests/test_block_shared_tree_edit.py -q` are green.

## Work Log
- 2026-06-23 [claude]: Shipped in commit 74178b82 — per-op worktree scope via `_git_dir_target`, Rule-5 realpath resolve in branch-guard & block-shared-tree-edit, push-target `--mirror`/`--all`/`+main` coverage.
- 2026-06-24 [claude]: File re-materialized from DB metadata (TASK-532); original body unrecoverable (never persisted to disk / git).
