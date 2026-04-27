#!/usr/bin/env bash
# PreToolUse hook: Block dangerous bash commands that could cause data loss.
# Source: AGENTS.md § Principles (P5), git safety
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")

if [[ "$TOOL" != "Bash" ]]; then
  exit 0
fi

cos_log_hook block-dangerous-commands fire "tool=Bash"
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")

# Block force push to main/master
if echo "$COMMAND" | grep -qE 'git push.*--force.*(main|master)'; then
  cos_log_hook block-dangerous-commands block "rule=force-push-main"
  echo "BLOCKED: Force push to main/master is extremely dangerous and can destroy shared history. Use a feature branch instead." >&2
  exit 2
fi
if echo "$COMMAND" | grep -qE 'git push.*-f.*(main|master)'; then
  cos_log_hook block-dangerous-commands block "rule=force-push-main-short"
  echo "BLOCKED: Force push to main/master is extremely dangerous. Use a feature branch instead." >&2
  exit 2
fi

# Block dropping database tables
if echo "$COMMAND" | grep -qiE 'DROP\s+(TABLE|DATABASE)'; then
  cos_log_hook block-dangerous-commands block "rule=drop-db"
  echo "BLOCKED: DROP TABLE/DATABASE is destructive and irreversible. If this is intentional, ask the user to confirm and run it manually." >&2
  exit 2
fi

# Block rm -rf on project root or critical directories
if echo "$COMMAND" | grep -qE 'rm -rf\s+(/|\.|\.\.|backend|frontend|docs|infrastructure)\b'; then
  cos_log_hook block-dangerous-commands block "rule=rm-rf-root"
  echo "BLOCKED: rm -rf on project directories is destructive. Be specific about which files to remove." >&2
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
