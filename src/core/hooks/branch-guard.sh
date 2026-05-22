#!/usr/bin/env bash
# branch-guard.sh (Phase gate) — enforce trunk-based git integrity.
#
# PreToolUse:Bash hook. In trunk mode (default) it BLOCKs commands that
# either (a) create a branch / worktree or (b) rewrite shared HEAD —
# both classes can clobber a peer session's commits or scatter work
# across phantom branches. The coding-os workflow commits directly to
# main; see src/core/rules/git-workflow.md. Set COS_GIT_WORKFLOW=pr to
# allow branches (future multi-developer mode).
#
# Always allowed: bare reset (unstage), `git reset --mixed HEAD`, file
# restore via `git checkout -- <path>` or `git checkout HEAD <path>`,
# `git checkout main` / `git switch main` (idempotent), branch list /
# delete / rename. Fail-closed on anything that moves HEAD or creates
# refs.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
if [[ "$TOOL" != "Bash" ]]; then
  exit 0
fi

# pr mode = branches + HEAD-moves allowed; the seam for future team workflows.
if [[ "${COS_GIT_WORKFLOW:-trunk}" == "pr" ]]; then
  exit 0
fi

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")
[[ -z "$COMMAND" ]] && exit 0

cos_log_hook branch-guard fire "tool=Bash"

# Returns 0 if `git reset` form would move HEAD (HEAD~, sha, branch ref).
# Returns 1 for safe forms: bare reset, `reset HEAD`, `reset -- <path>`.
# Pure bash case-statement parsing — POSIX ERE in bash has no `\b`.
_reset_is_head_move() {
  local cmd="$1"
  case "$cmd" in *"git reset"*) ;; *) return 1 ;; esac
  local seg="${cmd#*git reset}"
  seg="${seg%%[&|;]*}"
  seg="${seg#"${seg%%[![:space:]]*}"}"  # ltrim
  # Strip any leading --soft/--mixed/--keep/--patch/--hard flag(s).
  while :; do
    case "$seg" in
      --soft[[:space:]]*|--mixed[[:space:]]*|--keep[[:space:]]*|--patch[[:space:]]*|--hard[[:space:]]*)
        seg="${seg#* }"
        seg="${seg#"${seg%%[![:space:]]*}"}"
        ;;
      --soft|--mixed|--keep|--patch|--hard) seg=""; break ;;
      *) break ;;
    esac
  done
  seg="${seg%"${seg##*[![:space:]]}"}"  # rtrim
  case "$seg" in
    "") return 1 ;;                            # bare reset → unstage, no move
    --*) return 1 ;;                           # `-- <path>` → unstage path
    HEAD~*|HEAD^*|HEAD@*) return 0 ;;          # HEAD~/HEAD^/HEAD@ → moves HEAD
    HEAD) return 1 ;;                          # HEAD alone → no move
    "HEAD "*) return 1 ;;                      # HEAD followed by path → unstage from HEAD
    *) return 0 ;;                             # sha / branch / other ref → moves HEAD
  esac
}

# Returns 0 if `git checkout` form switches branches / detaches HEAD.
# Returns 1 for: branch-create (caught upstream), file restore, idempotent main/HEAD.
_checkout_is_head_move() {
  local cmd="$1"
  case "$cmd" in *"git checkout"*) ;; *) return 1 ;; esac
  # Branch creation (-b/-B) is handled by the earlier branch-create rule.
  case "$cmd" in
    *"git checkout "*"-b "*|*"git checkout "*"-B "*) return 1 ;;
  esac
  # File restore: contains ` -- ` separator or ends with ` --`.
  case "$cmd" in
    *" -- "*|*" --") return 1 ;;
  esac
  local seg="${cmd#*git checkout}"
  seg="${seg%%[&|;]*}"
  seg="${seg#"${seg%%[![:space:]]*}"}"
  local arg="" tok
  for tok in $seg; do
    if [[ "$tok" == "-" || "$tok" != -* ]]; then arg="$tok"; break; fi
  done
  case "$arg" in
    ""|main|HEAD) return 1 ;;                  # idempotent / HEAD-stable
    *) return 0 ;;                             # branch / sha / `-` (prev) / HEAD~ → moves HEAD
  esac
}

# Returns 0 if `git switch` form moves to a non-main branch / `-` / detached.
# Returns 1 for: branch-create (caught upstream), `switch main`.
_switch_is_branch_move() {
  local cmd="$1"
  case "$cmd" in *"git switch"*) ;; *) return 1 ;; esac
  case "$cmd" in
    *"git switch "*"-c "*|*"git switch "*"-C "*) return 1 ;;
  esac
  local seg="${cmd#*git switch}"
  seg="${seg%%[&|;]*}"
  seg="${seg#"${seg%%[![:space:]]*}"}"
  local arg="" tok
  for tok in $seg; do
    if [[ "$tok" == "-" || "$tok" != -* ]]; then arg="$tok"; break; fi
  done
  case "$arg" in
    ""|main) return 1 ;;
    *) return 0 ;;                             # branch / `-` (prev) → moves HEAD
  esac
}

REASON=""
# Branch / worktree creation (TASK-012 originals).
if echo "$COMMAND" | grep -qE 'git +(checkout|switch) +.*-[bBcC]\b'; then
  REASON="branch-create-checkout"
elif echo "$COMMAND" | grep -qE 'git +branch +[A-Za-z0-9._/]'; then
  REASON="branch-create"
elif echo "$COMMAND" | grep -qE 'git +worktree +add\b'; then
  REASON="worktree-add"
# HEAD-rewriting ops (TASK-013).
elif _reset_is_head_move "$COMMAND"; then
  REASON="reset-head-rewrite"
elif _checkout_is_head_move "$COMMAND"; then
  REASON="checkout-branch-switch"
elif _switch_is_branch_move "$COMMAND"; then
  REASON="switch-branch"
fi

if [[ -n "$REASON" ]]; then
  cos_log_hook branch-guard block "rule=${REASON}"
  bash "$(dirname "$0")/../scripts/log-write.sh" \
    --type "hook-block" --msg "branch-guard" --what "$REASON" 2>/dev/null || true
  {
    case "$REASON" in
      reset-head-rewrite)
        echo "BLOCKED: this 'git reset' would move HEAD — in trunk mode"
        echo "moving HEAD off a published commit clobbers peer work."
        echo ""
        echo "  Safe forms: 'git reset' (unstage), 'git reset --mixed HEAD',"
        echo "  'git reset -- <path>' (unstage one path)."
        echo "  To undo the last commit: 'git revert HEAD' (new commit,"
        echo "  preserves history)."
        ;;
      checkout-branch-switch)
        echo "BLOCKED: this 'git checkout' switches branches — coding-os"
        echo "uses a trunk-based workflow (main only)."
        echo ""
        echo "  To restore a file: 'git restore <path>' or"
        echo "  'git checkout -- <path>' (note the '--' separator)."
        echo "  To go to main: 'git switch main'."
        ;;
      switch-branch)
        echo "BLOCKED: this 'git switch' moves off main — coding-os uses"
        echo "a trunk-based workflow."
        echo ""
        echo "  Only 'git switch main' is allowed in trunk mode."
        ;;
      *)
        echo "BLOCKED: coding-os uses a trunk-based git workflow — commit"
        echo "directly to main, do not create branches or worktrees."
        echo ""
        echo "  To fix: edit files, then 'git commit <explicit paths>' and"
        echo "  'git pull --rebase origin main && git push origin main'."
        ;;
    esac
    echo ""
    echo "  See src/core/rules/git-workflow.md for the full rule."
    echo "  If the USER explicitly asked for this, re-run with"
    echo "  COS_GIT_WORKFLOW=pr set for that command."
  } >&2
  exit 2
fi

cos_log_hook branch-guard ok || true
exit 0
