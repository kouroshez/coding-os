#!/usr/bin/env bash
# PreToolUse hook: Block dangerous bash commands that could cause data loss.
# Source: AGENTS.md § Principles (P5), git safety
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

# Resolve a _helpers/<name> path through THIS hook's symlink chain — the
# .claude/.codex symlink points at the .sh only, not the _helpers/ tree, so a
# $(dirname "$0")-relative path misses. Echoes the absolute helper path.
_resolve_helper() {
  local src="${BASH_SOURCE[0]}" dir
  while [ -L "$src" ]; do
    dir="$(cd -P "$(dirname "$src")" && pwd)"
    src="$(readlink "$src")"
    [[ "$src" != /* ]] && src="${dir}/${src}"
  done
  printf '%s' "$(cd -P "$(dirname "$src")" && pwd)/_helpers/$1"
}

# Fail-closed: a data-loss gate that cannot read the command must DENY,
# not silently allow when jq is absent (observability-eye I8).
cos_require_parser block-dangerous-commands

INPUT="$(cos_read_stdin_bounded 2)"

# Fast-path: this gate fires on EVERY Bash command. The common case (no
# dangerous verb anywhere in the payload) must cost zero jq/python spawns.
# Every block below keys on one of these literals; if the raw payload mentions
# none of them there is nothing to deny — bail before parsing. (`rm`/`mv` etc.
# are still parsed properly downstream; this only short-circuits the no-match.)
# Indirection tokens (eval/xargs/<<</|sh) and hub-settings.json are included so an
# indirection-wrapped dangerous op or a policy-file write is never fast-skipped.
case "$INPUT" in
  *"git push"*|*"git reset"*|*"git clean"*|*rm*|*migrate*|*DROP*|*Drop*|*drop*|*eval*|*xargs*|*"<<<"*|*"|sh"*|*"| sh"*|*"|bash"*|*"| bash"*|*hub-settings.json*) ;;
  *) exit 0 ;;
esac

TOOL=$(printf '%s' "$INPUT" | cos_json_field tool_name)

if [[ "$TOOL" != "Bash" ]]; then
  exit 0
fi

cos_log_hook block-dangerous-commands fire "tool=Bash"
COMMAND=$(printf '%s' "$INPUT" | cos_json_field tool_input.command)

# Block a Bash write to the git-policy file: rewriting
# .coding-os/hub-settings.json from a shell self-downgrades pr-mode -> trunk,
# where a non-force push to main is legal. Gated on the basename so non-policy
# commands skip the python spawn. Defense-in-depth — fails OPEN on helper error;
# the authoritative wall is server-side branch protection.
case "$COMMAND" in
  *hub-settings.json*)
    SET_VERDICT=$(printf '%s' "$INPUT" | python3 "$(_resolve_helper check_settings_write.py)" 2>/dev/null || echo allow)
    if [ "$SET_VERDICT" = "block" ]; then
      cos_log_hook block-dangerous-commands block "rule=settings-policy-write"
      echo "BLOCKED: writing .coding-os/hub-settings.json from a shell flips the git workflow (pr<->trunk). Change git settings only via the Hub Config->Git tab — it is the policy file branch-guard reads on every hook." >&2
      exit 2
    fi
    ;;
esac

# Shell-indirection recovery: un-glue git commands hidden inside
# eval / pipe-into-sh / here-string / xargs so the force-push / reset / clean
# greps below see them. Gated on an indirection token so the common path spawns
# no python. branch-guard is the fail-closed twin for the protected ops.
COMMAND_SCAN="$COMMAND"
case "$COMMAND" in
  *eval*|*xargs*|*"<<<"*|*"|sh"*|*"| sh"*|*"|bash"*|*"| bash"*)
    _RECOVERED=$(printf '%s' "$INPUT" | python3 "$(_resolve_helper recover_indirect.py)" 2>/dev/null || true)
    [[ -n "$_RECOVERED" ]] && COMMAND_SCAN="$COMMAND"$'\n'"$_RECOVERED"
    unset _RECOVERED
    ;;
esac

# Block force push to main/master. Opt-in escape hatch for legitimate cases
# (pre-public history scrub, secret removal, BFG-style cleanup): EXPORT
# COS_ALLOW_FORCE_PUSH_MAIN=1 into the session env before the call. An inline
# `COS_ALLOW_FORCE_PUSH_MAIN=1 git push …` prefix does NOT work and is rejected
# by design — the assignment has not executed when this PreToolUse hook reads
# its own process env, so an agent cannot self-grant the override from the
# command string ( F3). Only a deliberate operator session-export opens it.
_FORCE_PUSH_OPT_IN=0
if [[ "${COS_ALLOW_FORCE_PUSH_MAIN:-0}" == "1" ]]; then
  _FORCE_PUSH_OPT_IN=1
fi
if [[ "$_FORCE_PUSH_OPT_IN" != "1" ]]; then
  # Force-push to main/master. git IGNORES flag position, so detect the push, the
  # force flag, and the main/master target INDEPENDENTLY — the old `--force.*main`
  # regex missed `git push origin main --force` / `... main -f` (flag AFTER the
  # refspec). `--force-with-lease` is the safe variant (and the pr-mode submit
  # path) so the boundary `--force([space]|$)` deliberately excludes it.
  if echo "$COMMAND_SCAN" | grep -qE '(^|[[:space:];&|])git[[:space:]]+push' \
     && echo "$COMMAND_SCAN" | grep -qE '(--force([[:space:]]|$)|(^|[[:space:]])-f([[:space:]]|$))' \
     && echo "$COMMAND_SCAN" | grep -qE '(^|[[:space:]/+:])(main|master)([[:space:]]|$)'; then
    cos_log_hook block-dangerous-commands block "rule=force-push-main"
    echo "BLOCKED: Force push to main/master is extremely dangerous and can destroy shared history. Use a feature branch instead. (Override: export COS_ALLOW_FORCE_PUSH_MAIN=1 session-wide; an inline prefix is rejected.)" >&2
    exit 2
  fi
  # Force via refspec: `+main` / `+HEAD:main` / `+refs/heads/main` (any qualifier —
  # the old regex needed a colon, so the fully-qualified `+refs/heads/main` slipped).
  if echo "$COMMAND_SCAN" | grep -qE '(^|[[:space:];&|])git[[:space:]]+push[^|;&]*[[:space:]]\+[^[:space:]]*(main|master)\b'; then
    cos_log_hook block-dangerous-commands block "rule=force-push-main-refspec"
    echo "BLOCKED: force-push refspec (+main/+master) rewrites shared history. Use a feature branch instead. (Override: export COS_ALLOW_FORCE_PUSH_MAIN=1 session-wide; an inline prefix is rejected.)" >&2
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
RM_VERDICT=$(printf '%s' "$INPUT" | python3 "$(_resolve_helper check_dangerous_rm.py)" 2>/dev/null || echo error)
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

# Block destructive `git reset --hard` / `git clean -f`. Delegated to a
# shlex-correct helper so a long-option ABBREVIATION (`reset --har`, `clean
# --for`/`--f`) or a split short cluster (`clean -d -f`) can't slip the old
# literal greps — git resolves any unambiguous prefix. Fed COMMAND_SCAN so a
# recovered-indirection git op is scanned too. Fails OPEN on helper error;
# branch-guard is the fail-closed twin for the HEAD-moving reset.
if echo "$COMMAND_SCAN" | grep -qE 'git[[:space:]]+(reset|clean)'; then
  # The envelope is built by the helper itself (--command) rather than by
  # `jq -n --arg`: a jq-less image made this substitution empty, the helper saw
  # no command and answered "allow", and `git reset --hard` walked through.
  DESTRUCTIVE_VERDICT=$(
    python3 "$(_resolve_helper check_git_destructive.py)" --command "$COMMAND_SCAN" \
      2>/dev/null || echo allow
  )
  if [ "$DESTRUCTIVE_VERDICT" = "reset-hard" ]; then
    cos_log_hook block-dangerous-commands block "rule=reset-hard"
    echo "BLOCKED: git reset --hard discards all uncommitted changes permanently. Consider 'git stash' instead, or ask the user to confirm." >&2
    exit 2
  fi
  if [ "$DESTRUCTIVE_VERDICT" = "clean-force" ]; then
    cos_log_hook block-dangerous-commands block "rule=git-clean-force"
    echo "BLOCKED: git clean -f permanently deletes untracked files. Ask the user to confirm which files should be removed." >&2
    exit 2
  fi
fi

exit 0
