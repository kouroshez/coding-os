---
id: TASK-515
title: "Route worktree state to the main repo's COS_STATE_DIR (fix $HOME hard-stop; share test-governor lock)"
swimlane: core
kind: feature
epic: multi-agent-pr-mode
labels: [pr-mode, state-files, foundation, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-22
started: 2026-06-22
completed: 2026-06-22
agent_session: ses-claude-20260622-134704-4de9
depends_on: [TASK-514]
blocked_by: []
references: []
---
# TASK-515: Route worktree state to the main repo's COS_STATE_DIR (fix $HOME hard-stop; share test-governor lock)

**Outcome (one sentence):** Every command run inside a git worktree resolves state/DB/board/presence to the MAIN repo (not the global hub), and all worktrees of one repo share one .test-run.lock + .last-verify.json. Eliminates the confirmed $HOME-hard-stop misroute (cos-env.sh::_cos_find_project_root breaks at $HOME, so ~/.coding-os/worktrees/* binds to the hub) and the test-governor pgrep-global fragmentation. This is the foundation every other pr-mode phase depends on.

## Read First
- src/core/hooks/cos-env.sh
- docs/engineering/state-files.md
- src/core/hooks/test-governor.sh
- src/core/hooks/_helpers/git_index_lock.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a hook firing with cwd under ~/.coding-os/worktrees/<slug>/ AND COS_PROJECT_ROOT exported to the main repo, **When** state resolves, **Then** COS_STATE_DIR == <main-repo>/.coding-os (not $HOME/.coding-os). **Given** a hook that would resolve COS_STATE_DIR to $HOME/.coding-os while cwd is under a worktrees/ path, **When** detected, **Then** it refuses and surfaces the misroute instead of silently writing to the hub. **Given** tests/test_panel_isolation.py plus a new worktree-shared-state case, **When** run, **Then** green.

## Work Log
- 2026-06-23 [claude]: Edit cos-env.sh
- 2026-06-23 [claude]: Edit cos-env.sh
- 2026-06-23 [claude]: Edit test_panel_isolation.py
- 2026-06-23 [claude]: commit 36e841a784 — feat(pr-mode): route git-worktree state to the main repo COS_STATE_DIR
- 2026-06-23 [claude]: cos-env.sh: added _cos_main_repo_from_worktree (git --git-common-dir, set-e-safe return-0) + a post-case worktree…
