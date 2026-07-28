---
id: TASK-614
title: "Add a local-autonomous autonomy rung: agent merges its own branch to LOCAL main after local tests, zero GitHub, no orphans"
swimlane: core
kind: feature
epic: git-foundation-hardening
labels: [pr-mode, autonomy, local, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-27
started: 2026-06-27
completed: 2026-06-27
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-614: Add a local-autonomous autonomy rung: agent merges its own branch to LOCAL main after local tests, zero GitHub, no orphans

**Outcome (one sentence):** Add a `local_autonomous` autonomy rung so a no-GitHub solo dev gets a hands-off loop (agent's branch lands on LOCAL integration after the agent's own verify passes, then worktree+branch are cleaned — zero push/PR/CI), implemented via a SANCTIONED `cos pr` land path with an explicit, narrowly-scoped branch-guard carve, because landing onto the shared integration checkout is a HEAD-move that branch-guard correctly blocks today.

## Read First
- src/cli/pr_commands.py
- src/core/hooks/_helpers/branch_guard_check.py
- src/core/hooks/branch-guard.sh
- src/core/web/routes/settings.py
- docs/playbooks/pr-workflow.md

## Repro Steps
Workflow whdjyvqjq + review (agent: FLAWED — seam under-specified). Verified: `_AUTONOMY_LEVELS = ("local","draft","auto_merge","autonomous")` (pr_commands.py:153) — no local_autonomous; the `local` rung short-circuits commit-only (~566-597, never pushes); settings.py `_GitSettingsIn.autonomy_level` is a `Literal[...4 rungs]` (must be extended too). CRITICAL design fact the first draft missed: landing the agent branch onto LOCAL integration means moving integration's HEAD on the SHARED checkout, which `_evaluate_pr` in branch_guard_check.py BLOCKs; a merge run *inside the worktree* (`git -C <wt> merge integration`) is worktree-scoped+allowed but merges the WRONG direction (integration→branch, not branch→main). So a real sanctioned land path + a guard carve is the core work, not an afterthought.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** autonomy_level=local_autonomous and a GREEN local verify in the worktree, **When** the agent finishes, **Then** a sanctioned `cos pr` land operation fast-forwards/merges --no-ff the agents/* branch onto LOCAL integration and removes the worktree+branch (zero orphans, zero network). **Given** branch-guard is active, **When** that sanctioned land runs (identified by a cos-set signal, e.g. an env the cos command exports, NOT a flag the agent can forge), **Then** it is ALLOWED while a raw `git merge`/`git reset`/`git update-ref` by the agent on the shared checkout stays BLOCKED — prove BOTH in tests. **Given** a RED local verify or a merge conflict, **Then** it does NOT land (commit stays on the branch; conflict → `merge --abort`, surfaced). **Given** the new rung, **Then** `_AUTONOMY_LEVELS` and the settings.py `_GitSettingsIn` Literal both include it. Verify: `uv run pytest tests/test_cli.py::TestCosPr tests/test_branch_guard.py -q` with land-green / land-blocked-for-raw-agent / red-no-land / conflict-abort cases.

## Work Log
- 2026-06-28 [claude]: Shipped local_autonomous: (1) rung added to _AUTONOMY_LEVELS (pr_commands) + settings.py _GitSettingsIn Literal; (2)…
