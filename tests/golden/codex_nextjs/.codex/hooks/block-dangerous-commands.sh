#!/usr/bin/env bash
# PreToolUse hook: Block dangerous bash commands that could cause data loss.
# Source: AGENTS.md § Principles (P5), git safety
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

# Fail-closed: a data-loss gate that cannot read the command must DENY,
# not silently allow when jq is absent (observability-eye I8).
cos_require_parser block-dangerous-commands

INPUT="$(cos_read_stdin_bounded 2)"

# Fast-path: this gate fires on EVERY Bash command. The common case (no
# dangerous verb anywhere in the payload) must cost zero jq/python spawns.
# Every block below keys on one of these literals; if the raw payload mentions
# none of them there is nothing to deny — bail before parsing. (`rm`/`mv` etc.
# are still parsed properly downstream; this only short-circuits the no-match.)
case "$INPUT" in
  *"git push"*|*"git reset"*|*"git clean"*|*rm*|*migrate*|*DROP*|*Drop*|*drop*) ;;
  *) exit 0 ;;
esac

TOOL=$(printf '%s' "$INPUT" | cos_json_field tool_name)

if [[ "$TOOL" != "Bash" ]]; then
  exit 0
fi

cos_log_hook block-dangerous-commands fire "tool=Bash"
COMMAND=$(printf '%s' "$INPUT" | cos_json_field tool_input.command)

# Block force push to main/master. Opt-in escape hatch for legitimate cases
# (pre-public history scrub, secret removal, BFG-style cleanup): prefix the
# command with COS_ALLOW_FORCE_PUSH_MAIN=1 (or export it before the call).
_FORCE_PUSH_OPT_IN=0
if [[ "${COS_ALLOW_FORCE_PUSH_MAIN:-0}" == "1" ]]; then
  _FORCE_PUSH_OPT_IN=1
fi
if echo "$COMMAND" | grep -qE '(^|[[:space:];&|])COS_ALLOW_FORCE_PUSH_MAIN=1\b'; then
  _FORCE_PUSH_OPT_IN=1
fi
if [[ "$_FORCE_PUSH_OPT_IN" != "1" ]]; then
  if echo "$COMMAND" | grep -qE 'git push.*--force.*(main|master)'; then
    cos_log_hook block-dangerous-commands block "rule=force-push-main"
    echo "BLOCKED: Force push to main/master is extremely dangerous and can destroy shared history. Use a feature branch instead. (Override: COS_ALLOW_FORCE_PUSH_MAIN=1)" >&2
    exit 2
  fi
  if echo "$COMMAND" | grep -qE 'git push.*-f.*(main|master)'; then
    cos_log_hook block-dangerous-commands block "rule=force-push-main-short"
    echo "BLOCKED: Force push to main/master is extremely dangerous. Use a feature branch instead. (Override: COS_ALLOW_FORCE_PUSH_MAIN=1)" >&2
    exit 2
  fi
  # Refspec force: `git push origin +main` / `+HEAD:main` rewrites history too.
  if echo "$COMMAND" | grep -qE 'git push[^|;&]*[[:space:]]\+([^[:space:]]*:)?(main|master)\b'; then
    cos_log_hook block-dangerous-commands block "rule=force-push-main-refspec"
    echo "BLOCKED: force-push refspec (+main/+master) rewrites shared history. Use a feature branch instead. (Override: COS_ALLOW_FORCE_PUSH_MAIN=1)" >&2
    exit 2
  fi
fi

# Block dropping database tables
if echo "$COMMAND" | grep -qiE 'DROP\s+(TABLE|DATABASE)'; then
  cos_log_hook block-dangerous-commands block "rule=drop-db"
  echo "BLOCKED: DROP TABLE/DATABASE is destructive and irreversible. If this is intentional, ask the user to confirm and run it manually." >&2
  exit 2
fi

# Block recursive rm of a critical path (root / cwd / parent / glob / project
# dirs / top-level absolute). Delegated to a shlex-correct helper so flag-order
# (-fr, -r -f) and bare /·.·..·* targets can't slip past a regex word-boundary.
# Skip the python helper spawn entirely when COMMAND has no `rm` token — the
# helper would return `allow` for a command with no rm, so this is a pure
# fast-path (saves a ~50ms python3 startup on every non-rm git/sql command).
case "$COMMAND" in
  *rm*) ;;
  *)
    # No rm at all → nothing for the helper to deny; fall through past the
    # rm gate to the remaining (migrate / reset / clean) checks.
    RM_VERDICT="allow"
    ;;
esac
if [ "${RM_VERDICT:-}" != "allow" ]; then
# Resolve the helper through the file's PHYSICAL location so it works through
# the .claude/hooks/ symlink — `$(dirname "$0")/_helpers` does NOT (the symlink
# points at the .sh only, not the _helpers tree). Same readlink dance as
# branch-guard; the old form silently never ran (masked by `|| echo allow`).
_rm_src="${BASH_SOURCE[0]}"
while [ -L "$_rm_src" ]; do
  _rm_dir="$(cd -P "$(dirname "$_rm_src")" && pwd)"
  _rm_src="$(readlink "$_rm_src")"
  [[ "$_rm_src" != /* ]] && _rm_src="${_rm_dir}/${_rm_src}"
done
RM_HELPER="$(cd -P "$(dirname "$_rm_src")" && pwd)/_helpers/check_dangerous_rm.py"
unset _rm_src _rm_dir

RM_VERDICT=$(printf '%s' "$INPUT" | python3 "$RM_HELPER" 2>/dev/null || echo error)
fi
# Fail-closed but SCOPED: a helper crash/absence (RM_VERDICT=error) blocks
# only when the command actually contains a recursive rm we could not verify —
# never brick unrelated commands (observability-eye I8/A2).
if [ "$RM_VERDICT" = "error" ]; then
  if echo "$COMMAND" | grep -qE '(^|[[:space:];&|])(sudo[[:space:]]+)?rm[[:space:]]+(-[A-Za-z]*[rR]|--recursive)'; then
    cos_say error hook.block_dangerous_commands "check_dangerous_rm helper unavailable — failing closed on a recursive rm" 2>/dev/null || true
    RM_VERDICT="block"
  else
    RM_VERDICT="allow"
  fi
fi
if [ "$RM_VERDICT" = "block" ]; then
  cos_log_hook block-dangerous-commands block "rule=rm-rf-critical"
  echo "BLOCKED: recursive rm targeting a critical path (/, ., .., *, a project dir, or a top-level directory). Name the exact files to remove, or ask the user to run it manually." >&2
  exit 2
fi

# Block direct migration apply to production
if echo "$COMMAND" | grep -qE 'manage\.py migrate.*--settings.*production'; then
  cos_log_hook block-dangerous-commands block "rule=prod-migrate"
  echo "BLOCKED: Production migrations require human execution (AGENTS.md P5). Ask the user to run this command manually." >&2
  exit 2
fi

# Block git reset --hard without user confirmation
if echo "$COMMAND" | grep -qE 'git reset --hard'; then
  cos_log_hook block-dangerous-commands block "rule=reset-hard"
  echo "BLOCKED: git reset --hard discards all uncommitted changes permanently. Consider 'git stash' instead, or ask the user to confirm." >&2
  exit 2
fi

# Block git clean -f (deletes untracked files)
if echo "$COMMAND" | grep -qE 'git clean\s+-[a-z]*f'; then
  cos_log_hook block-dangerous-commands block "rule=git-clean-force"
  echo "BLOCKED: git clean -f permanently deletes untracked files. Ask the user to confirm which files should be removed." >&2
  exit 2
fi

exit 0
