---
id: TASK-593
title: "Worktree dependency/secret bootstrap: cos pr open creates a fresh checkout with no node_modules/.env/pods so the repo validate command fails"
swimlane: core
kind: feature
epic: git-foundation-hardening
labels: [pr-mode, worktree, bootstrap, critic-found, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-26
started: 2026-06-26
completed: 2026-06-26
agent_session: ses-claude-20260625-235014-c028
depends_on: []
blocked_by: []
references: []
---
# TASK-593: Worktree dependency/secret bootstrap: cos pr open creates a fresh checkout with no node_modules/.env/pods so the repo validate command fails

**Outcome (one sentence):** Critic-found critical breakpoint (mobile / web / data real-world cases — the largest real gap). `cos pr open` does fetch + `git worktree add` + lock only (pr_commands.py:399-402); a worktree is a fresh checkout with NO gitignored deps (node_modules, .venv, vendor, Pods) and NO local secrets (.env, .env.local), so the agent's first `npm run validate` / `make verify` / `flutter test` fails on every fresh worktree — breaking the work+validate step (§4.2 of the loop) for almost every real project. Mirror Claude Code's native `.worktreeinclude` (confirmed via the 2026 Claude Code worktrees doc): an opt-in per-project list of gitignored paths to copy/symlink into a new worktree, plus an optional `worktree_setup_cmd` (e.g. `npm ci`) run once after creation. Keep it opt-in + reuse git_settings; do not auto-run arbitrary commands without consent.

## Read First
- src/cli/pr_commands.py
- docs/playbooks/pr-workflow.md
- src/core/web/routes/settings.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a project that declares a worktree-include list (e.g. .env, node_modules) and/or a setup command, **When** `cos pr open` creates a worktree, **Then** those gitignored paths are present (copied or symlinked) and the setup command has run, so the repo validate command succeeds. **Given** no such config (default), **When** `cos pr open` runs, **Then** behavior is byte-identical to today (no copy, no command). **Given** the include list, **When** the agent commits, **Then** the copied gitignored paths are NOT added to the PR (they stay gitignored). Verify: uv run pytest tests/test_cli.py::TestCosPr -q green + new tests.

## Work Log
- 2026-06-26 [claude]: Edit wt_exclude_test.sh
- 2026-06-26 [claude]: Plan: symlink (not copy) declared gitignored paths into a fresh worktree + write each to the worktree git exclude —…
- 2026-06-26 [claude]: Edit pr_commands.py
- 2026-06-26 [claude]: Edit pr_commands.py
- 2026-06-26 [claude]: Edit settings.py
- 2026-06-26 [claude]: Edit settings.py
- 2026-06-26 [claude]: Edit test_cli.py
- 2026-06-26 [claude]: Edit test_hub_settings_git.py
- 2026-06-26 [claude]: Edit test_hub_settings_git.py
- 2026-06-26 [claude]: Edit test_hub_settings_git.py
- 2026-06-26 [claude]: Edit pr-workflow.md
- 2026-06-26 [claude]: Edit pr-workflow.md
- 2026-06-26 [claude]: Edit multi-agent-git-use-cases.md
- 2026-06-26 [claude]: Edit pr_commands.py
- 2026-06-26 [claude]: Edit pr_commands.py
- 2026-06-26 [claude]: Edit pr_commands.py
- 2026-06-26 [claude]: Edit pr_commands.py
- 2026-06-26 [claude]: Edit settings.py
- 2026-06-26 [claude]: Edit settings.py
- 2026-06-26 [claude]: committed a2635f46 · 6 files
