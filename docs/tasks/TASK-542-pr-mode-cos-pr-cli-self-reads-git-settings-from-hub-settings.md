---
id: TASK-542
title: "pr-mode: cos pr CLI self-reads git_settings from hub-settings.json \u2014 COS_GIT_* never injected into the CLI process"
swimlane: core
kind: bug
epic: pr-mode-hardening
labels: [ready]
status: testing
priority: P1
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: null
agent_session: ses-claude-20260624-034200-e9e7
depends_on: []
blocked_by: []
references: []
---
# TASK-542: pr-mode: cos pr CLI self-reads git_settings from hub-settings.json — COS_GIT_* never injected into the CLI process

**Outcome (one sentence):** cos pr submit/open/cleanup honor the consumer's configured autonomy_level + integration_branch even though no process injects COS_GIT_* into the CLI shell (settings.template.json has no env key; cos-env.sh exports only inside hook subprocesses, and the agent's command shell has zero COS_* vars). `_autonomy_level()`/`_integration_branch()` fall back to reading git_settings from the MAIN repo's hub-settings.json (worktree-safe via `--git-common-dir` parent) when the env var is absent; an explicit env var always wins. The `local` rung no longer silently pushes; a `development` integration no longer silently targets `main`.

## Read First
- src/cli/pr_commands.py
- src/core/hooks/cos-env.sh
- docs/playbooks/pr-workflow.md

## Repro Steps
Set git_settings.autonomy_level=local in hub-settings.json; run `cos pr submit` with no COS_GIT_AUTONOMY in env → it pushes + opens a PR (draft path) instead of the local no-push path, because `_autonomy_level()` (pr_commands.py:103-105) reads only os.environ and nothing injects COS_GIT_AUTONOMY. Same for `_integration_branch()` silently defaulting to `main`.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** git_settings.autonomy_level=local and no COS_GIT_AUTONOMY in env, **When** cos pr submit runs, **Then** it takes the local (no-push, no-PR) path.
- **Given** git_settings.integration_branch=development and no COS_GIT_INTEGRATION_BRANCH in env, **When** cos pr open runs, **Then** the worktree bases on development and the PR --base targets development.
- **Given** COS_GIT_AUTONOMY=auto_merge set in env, **When** submit runs, **Then** env wins over the file (explicit override preserved).
- **Given** the CLI runs inside a linked worktree, **When** it reads settings, **Then** it resolves the MAIN repo's hub-settings.json, not the worktree's.

## Work Log
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit settings.py
- 2026-06-24 [claude]: Edit test_cli.py
- 2026-06-24 [claude]: Edit test_cli.py
- 2026-06-24 [claude]: Edit test_cli.py
- 2026-06-24 [claude]: Edit pr-workflow.md
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Added _git_settings()/_main_repo_root() to pr_commands.py; _integration_branch(repo)/_autonomy_level(repo) now fall…
