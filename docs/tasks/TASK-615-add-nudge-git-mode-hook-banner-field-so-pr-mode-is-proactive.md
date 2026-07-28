---
id: TASK-615
title: "Add nudge-git-mode hook + banner field so pr-mode is proactively surfaced to the agent, not learned by being blocked"
swimlane: infra
kind: feature
epic: git-foundation-hardening
labels: [pr-mode, hooks, propagation, ready]
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
# TASK-615: Add nudge-git-mode hook + banner field so pr-mode is proactively surfaced to the agent, not learned by being blocked

**Outcome (one sentence):** Config propagation is REACTIVE: nothing tells the agent pr-mode is on — it only discovers it when block-shared-tree-edit BLOCKs its first shared-tree edit, and a mid-session toggle flip changes the rails under a running agent with no warning. Add a `nudge-git-mode.sh` UserPromptSubmit hook (mirroring nudge-model-routing.sh) that, once per session when COS_GIT_WORKFLOW=pr, injects a directive ("this project is pr-mode — start with `cos pr open`, edit only inside the worktree"); add a git-mode field to USER_BANNER (session-context.sh) so the operator sees the mode each turn; and document the inherited-COS_GIT_WORKFLOW-wins caveat + the recommend-set-before-start guidance.

## Read First
- src/core/hooks/nudge-model-routing.sh
- src/core/hooks/session-context.sh
- src/core/hooks/cos-env.sh
- src/core/hooks/registry.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** COS_GIT_WORKFLOW=pr, **When** the session's first prompt is submitted, **Then** nudge-git-mode injects the pr-mode directive exactly once (not every turn). **Given** trunk mode (default), **When** any prompt is submitted, **Then** the hook is inert (no output, one cheap env check). **Given** any turn in pr-mode, **Then** USER_BANNER shows the git mode. Verify: a new tests/test_nudge_git_mode.py drives the hook with COS_GIT_WORKFLOW=pr/unset and asserts once-per-session + inert-in-trunk; `make verify-hooks` green; registry.yaml + adapter templates regenerated (make regen-adapter-templates).

## Work Log
- 2026-06-28 [claude]: Added nudge-git-mode.sh (mirrors nudge-model-routing: once-per-session pr-mode directive when COS_GIT_WORKFLOW=pr,…
