---
id: TASK-582
title: "Restore green main: worktree-misroute hub-collision regression (1f8869b5) + 2 stale docs-lint hook links"
swimlane: infra
kind: bug
epic: null
labels: [ci, pr-mode, state-isolation, docs-rot, green-main, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-26
started: 2026-06-25
completed: 2026-06-25
agent_session: ses-claude-20260625-203131-6294
depends_on: []
blocked_by: []
references: []
---
# TASK-582: Restore green main: worktree-misroute hub-collision regression (1f8869b5) + 2 stale docs-lint hook links

**Outcome (one sentence):** main is green again: a worktree whose main repo is unresolvable routes its COS_STATE_DIR to a per-worktree quarantine that is neither the global hub (no cross-project state collision) nor inside the worktree checkout (no stray .coding-os committed into the PR); and docs-lint has zero BROKEN-FILE findings.

## Read First
- src/core/hooks/cos-env.sh
- tests/test_panel_isolation.py
- docs/playbooks/hook-authoring.md

## Repro Steps
On main HEAD: `uv run pytest tests/test_panel_isolation.py::test_worktree_misroute_to_hub_is_refused` FAILS — _resolve_state_dir returns ($HOME/.coding-os, '1'); the assert state_dir != hub fails. Regression from 1f8869b5 (2026-06-23) which bound misrouted worktree state to the hub to avoid a stray .coding-os in the PR, breaking the earlier test (36e841a7, 2026-06-22). `make docs-lint` → FAIL: 2 BROKEN-FILE (hook-authoring.md, TASK-017 → deleted hooks).

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a git worktree under ~/.coding-os/worktrees with no COS_PROJECT_ROOT and no resolvable main repo, inheriting COS_STATE_DIR=$HOME/.coding-os, **When** cos-env.sh resolves state, **Then** COS_STATE_MISROUTE=1 is flagged AND COS_STATE_DIR != $HOME/.coding-os (steered to a per-worktree quarantine off the hub root) — test_worktree_misroute_to_hub_is_refused passes; **And** the happy paths (test_worktree_project_root_beats_claude_project_dir, test_worktree_git_recovery_without_project_root) still route to the main repo (no regression). **Given** docs-lint, **When** run, **Then** BROKEN-FILE count is 0 (hook-authoring.md + TASK-017 stale links to deleted auto-reindex-shell-ops.sh / auto-prune-deleted-files.sh corrected or removed).
Tests: uv run pytest tests/test_panel_isolation.py -q (green) + make verify-hooks + make docs-lint (no BROKEN-FILE).

## Work Log
- 2026-06-26 [claude]: Edit cos-env.sh
- 2026-06-26 [claude]: Edit hook-authoring.md
- 2026-06-26 [claude]: Edit TASK-017-fix-prune-deleted-path-missing-pragma-foreign-keys-on.md
- 2026-06-26 [claude]: commit fe315933d2 — fix(pr-mode): route misrouted worktree state to a per-worktree quarantine off the hub
- 2026-06-26 [claude]: Fixed both pre-existing reds. (1) cos-env.sh misroute branch: unresolvable-main worktree now steers COS_STATE_DIR to…
