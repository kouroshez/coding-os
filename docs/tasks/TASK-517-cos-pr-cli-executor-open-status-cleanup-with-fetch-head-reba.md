---
id: TASK-517
title: "cos pr CLI executor: open/status/cleanup with FETCH_HEAD rebase, sha-pinned lease, gc.auto=0, claim-derived branch id"
swimlane: core
kind: feature
epic: multi-agent-pr-mode
labels: [pr-mode, cli, executor, ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-06-22
started: null
completed: null
agent_session: null
depends_on: [TASK-516]
blocked_by: []
references: []
---

# TASK-517: cos pr CLI executor: open/status/cleanup with FETCH_HEAD rebase, sha-pinned lease, gc.auto=0, claim-derived branch id

**Outcome (one sentence):** A thin idempotent `cos pr` command group (open/status/cleanup) the agent calls in its own turn loop — NO kernel daemon (hooks can't loop, MCP polling blocks the server). `open` = cos_task_claim_next session → worktree at COS_WORKTREE_ROOT/<basename-sha8(realpath)>/<task>-<session> → branch agents/<task>/<session> → commit → fetch+rebase onto FETCH_HEAD (pinned, not the shared moving ref) → push --force-with-lease=<branch>:<sha> --force-if-includes → gh pr create → arm auto-merge ONLY if a required check exists. Supports adhoc/no-task work: when code work is requested WITHOUT a board task, `cos pr open --adhoc` still creates a worktree + agents/adhoc/<session> branch (one worktree per unit-of-work, not per file). gc.auto=0 + bounded retry on "cannot lock ref". Capability preflight (remote/gh/CI) with degrade-to-trunk. All gh-coupled code stays in src/cli, never src/core (P2/P8).

## Read First
- src/cli/board_commands.py
- src/core/board_os/mcp_tools.py
- src/cli/_init_helpers.py
- docs/playbooks/pr-workflow.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** pr-mode enabled with remote+gh+CI present, **When** `cos pr open` runs, **Then** a worktree under COS_WORKTREE_ROOT/<slug> + branch agents/<task>/<claim-session> is created, work is rebased onto FETCH_HEAD and pushed with a sha-pinned lease, and a PR is opened with auto-merge armed only when a required status check is detected. **Given** a code-work request with no board task, **When** `cos pr open --adhoc` runs, **Then** a worktree + agents/adhoc/<session> branch is created and the work is isolated exactly like a task-scoped run. **Given** no remote/gh/CI, **When** `cos pr open` runs preflight, **Then** it degrades to the trunk publish path and surfaces the missing capability instead of failing mid-loop. **Given** tests/test_cli.py new cos-pr cases, **Then** green.

## Work Log
