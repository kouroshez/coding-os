#!/usr/bin/env bash
# PreToolUse hook: Block dangerous bash commands that could cause data loss.
# Source: AGENTS.md § Principles (P5), git safety
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")

if [[ "$TOOL" != "Bash" ]]; then
  exit 0
fi

cos_log_hook block-dangerous-commands fire "tool=Bash"
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")

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
RM_VERDICT=$(echo "$INPUT" | python3 "$(dirname "$0")/_helpers/check_dangerous_rm.py" 2>/dev/null || echo allow)
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
