#!/usr/bin/env bash
# UserPromptSubmit hook — pr-mode directive injector (TASK-615).
#
# Config propagation is reactive: nothing tells the agent the project runs
# pr-mode — it only finds out when block-shared-tree-edit BLOCKs its first
# shared-tree edit, and a mid-session toggle flip changes the rails with no
# warning. When COS_GIT_WORKFLOW=pr, inject a ONE-LINE directive (once per
# session) so the agent starts with `cos pr open` and edits inside the
# worktree. Trunk (default) = silent exit before any output: zero injected
# tokens, zero behavior change. Fail-open: never blocks a prompt.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

[[ "${COS_GIT_WORKFLOW:-trunk}" == "pr" ]] || exit 0

# Once per session — same marker family as the other nudges; the panel dir is
# session-scoped (cleared at SessionStart) so a new session re-injects once.
MARKER="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.git-mode-nudged"
[[ -f "$MARKER" ]] && exit 0
touch "$MARKER" 2>/dev/null || true

CONTEXT="[pr-mode ON] This project's git workflow is pr (COS_GIT_WORKFLOW=pr): do NOT edit the shared checkout — start with 'cos pr open' (or --adhoc), work INSIDE the worktree, then 'cos pr submit' and drive CI with Skill pr-mode-driver. Direct edits/commits to the shared tree are branch-guard / block-shared-tree-edit BLOCKed. Contract: docs/playbooks/pr-workflow.md"

cos_log_hook nudge-git-mode ok || true
printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":$(printf '%s' "$CONTEXT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}"

exit 0
