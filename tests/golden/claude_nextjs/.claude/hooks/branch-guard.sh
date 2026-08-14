#!/usr/bin/env bash
# branch-guard.sh — enforce trunk-based git integrity.
#
# PreToolUse:Bash hook. In trunk mode (default) it BLOCKs commands that
# either (a) create a branch / worktree or (b) rewrite shared HEAD —
# both classes can clobber a peer session's commits or scatter work
# across phantom branches. The coding-os workflow commits directly to
# main (see src/core/rules/git-workflow.md). COS_GIT_WORKFLOW=pr switches to a
# positive pr-mode policy (consumer-only): agents/* branches + worktrees pass,
# but the shared checkout and protected branches stay guarded — NOT a bypass.
#
# The actual parsing lives in _helpers/branch_guard_check.py — it
# handles whitespace normalization, `git -C` / `git -c` global options,
# nested `sh -c "..."` / `bash -c "..."`, command-segment splitting,
# and `shlex` quoting (so literal `git reset HEAD~1` inside an `echo`
# or `grep` arg does NOT trigger). This script is a thin wrapper:
# fast-skip when "git" isn't in the command, otherwise dispatch to the
# helper and act on its JSON verdict.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

# Fail-closed: a branch/HEAD-move guard that cannot read the command must DENY
# (observability-eye I8). python3 fallback keeps it working without jq.
cos_require_parser branch-guard

INPUT="$(cos_read_stdin_bounded 2)"

# Fast-path: every branch/HEAD-move this guard blocks is a `git` command. If
# the raw payload has no "git" substring at all there is nothing to deny —
# bail before any jq spawn (this gate fires on EVERY Bash command).
case "$INPUT" in
  *git*) ;;
  *) exit 0 ;;
esac

TOOL=$(printf '%s' "$INPUT" | cos_json_field tool_name)
if [[ "$TOOL" != "Bash" ]]; then
  exit 0
fi

# pr-mode is NOT a guard-kill. The command flows into branch_guard_check.py,
# which applies a positive pr-mode policy: allow agents/* branch + worktree-add,
# but still BLOCK HEAD-rewrites/commits on the shared integration checkout and
# pushes to protected branches. SPEC: docs/playbooks/pr-workflow.md § 5.

COMMAND=$(printf '%s' "$INPUT" | cos_json_field tool_input.command)
[[ -z "$COMMAND" ]] && exit 0

# Fast-skip: no "git" substring → no risk; skip the python startup cost.
if [[ "$COMMAND" != *git* ]]; then
  exit 0
fi

cos_log_hook branch-guard fire "tool=Bash"

# Resolve the helper through the file's physical location — works through
# the .claude/hooks/ symlinks that consumer projects install.
_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
  _dir="$(cd -P "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ "$_src" != /* ]] && _src="${_dir}/${_src}"
done
HOOKS_PHYS_DIR="$(cd -P "$(dirname "$_src")" && pwd)"
unset _src _dir
HELPER="${HOOKS_PHYS_DIR}/_helpers/branch_guard_check.py"

if [[ ! -f "$HELPER" ]]; then
  # Fail-CLOSED: we are past the fast-skip, so the command IS git-related.
  # A missing helper (dangling symlink / broken install) means we cannot
  # verify it — deny rather than silently allow (observability-eye I8/A2).
  cos_say error hook.branch_guard "branch-guard helper missing — failing closed on git command" 2>/dev/null || true
  cos_log_hook branch-guard block "rule=helper-missing"
  echo "BLOCKED: branch-guard helper missing ($HELPER) — cannot verify this git command; failing closed." >&2
  echo "  Restore src/core/hooks/_helpers/branch_guard_check.py (fail-closed: pr-mode does not bypass this guard)." >&2
  exit 2
fi

# Run the helper, capturing BOTH stdout (verdict) and stderr (crash detail).
# We are past the fast-skip, so the command IS git-related: a guard that
# cannot evaluate it must NOT silently allow (the old `2>/dev/null || allow`
# was a fail-OPEN security inversion — the guard silently stopped guarding,
# crash recorded nowhere). On helper failure we fail CLOSED and surface the
# crash to the eye. No non-git blast radius: non-git Bash exited at the fast-skip.
HELPER_ERR=$(mktemp)
HELPER_RC=0
VERDICT_JSON=$(printf '%s' "$INPUT" | python3 "$HELPER" 2>"$HELPER_ERR") || HELPER_RC=$?
HELPER_STDERR=$(cat "$HELPER_ERR" 2>/dev/null || true); rm -f "$HELPER_ERR"

if [[ "$HELPER_RC" -ne 0 || -z "$VERDICT_JSON" ]]; then
  cos_say error hook.branch_guard "branch-guard helper failed (rc=${HELPER_RC}) — failing closed on git command" detail="${HELPER_STDERR:0:200}" 2>/dev/null || true
  cos_log_hook branch-guard block "rule=helper-crash rc=${HELPER_RC}" || true
  echo "BLOCKED: branch-guard helper failed (rc=${HELPER_RC}) — cannot verify this git command; failing closed." >&2
  echo "  Fix src/core/hooks/_helpers/branch_guard_check.py (fail-closed: pr-mode does not bypass this guard)." >&2
  [[ -n "$HELPER_STDERR" ]] && echo "  helper stderr: ${HELPER_STDERR}" >&2
  exit 2
fi

# Read the verdict through cos_json_field (jq → python3), never raw jq: a bare
# `jq -r … || echo block` exits 127 when jq is absent, and 127 is not 2, so the
# runtime treats it as a hook error and lets the git command through — the same
# fail-open class this guard already closes for a crashed helper. Absent or
# unreadable verdict stays "block" (observability-eye I8).
VERDICT=$(printf '%s' "$VERDICT_JSON" | cos_json_field verdict)
VERDICT="${VERDICT:-block}"

if [[ "$VERDICT" != "block" ]]; then
  cos_log_hook branch-guard ok || true
  exit 0
fi

REASON=$(printf '%s' "$VERDICT_JSON" | cos_json_field reason)
REASON="${REASON:-branch-guard-block}"
MESSAGE=$(printf '%s' "$VERDICT_JSON" | cos_json_field message)

cos_log_hook branch-guard block "rule=${REASON}"
bash "$(dirname "$0")/../scripts/log-write.sh" \
  --type "hook-block" --msg "branch-guard" --what "$REASON" 2>/dev/null || true

echo "WHY: trunk-based git keeps history linear and the blast radius reviewable — src/core/ edits reach every consumer via live symlinks." >&2
if [[ -n "$MESSAGE" ]]; then
  printf '%s\n' "$MESSAGE" >&2
else
  echo "BLOCKED: coding-os trunk-based git workflow forbids this command." >&2
  echo "  See src/core/rules/git-workflow.md (pr-mode applies a positive policy, not a bypass)." >&2
fi
exit 2
