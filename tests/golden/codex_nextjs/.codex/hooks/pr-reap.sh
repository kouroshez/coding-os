#!/usr/bin/env bash
# pr-reap.sh — SessionStart orphan-reaper trigger (pr-mode only).
#
# Cleanup must be owner-independent: a crashed agent never runs its own
# `cos pr cleanup` (the exact Rule-21 failure mode). On every SessionStart a
# live session sweeps the repo's worktrees and GCs the ones whose owning session
# is presence-offline (worktree + local/remote branch + PR), and drains the
# pending-cleanup ledger. Fire-and-forget so SessionStart never blocks on git/gh
# network calls. Inert in trunk mode (the default) → one env check and exit.
# SPEC: docs/playbooks/pr-workflow.md § 7.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

# Inert unless pr-mode.
[[ "${COS_GIT_WORKFLOW:-trunk}" == "pr" ]] || exit 0
command -v cos >/dev/null 2>&1 || exit 0

cos_log_hook pr-reap fire "sweeping offline worktrees"
# Detach so a slow git/gh sweep can never delay the session.
( cos pr reap >/dev/null 2>&1 & ) || true
exit 0
