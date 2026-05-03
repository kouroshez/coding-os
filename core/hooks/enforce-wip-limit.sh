#!/usr/bin/env bash
# Phase L.4 — PreToolUse: before transition to in_progress/emergency
# Checks current WIP count against cap from scrumban-config.yaml.
# Blocks if cap exceeded; env COS_WIP_OVERRIDE=1 bypasses.

set -euo pipefail
source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi


cos_log_hook "enforce-wip-limit" "entry" 2>/dev/null || true

# WIP check runs through the same workflow.transition() path that MCP
# calls — bash-level hook is a belt-and-suspenders layer for the case
# where a task file is edited directly (bypassing cos_task_move).
# If board_os + config are unavailable, fail-soft.

payload="$(cos_read_stdin_bounded 5)"
file_path="$(echo "$payload" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get("tool_input", {}).get("file_path", ""))
except Exception:
    print("")
' 2>/dev/null || echo "")"

if [[ "$file_path" != *"docs/tasks/"*.md ]]; then
    exit 0
fi

# bash 5.3.9 deadlocks `python3 - <<HEREDOC`; helper file is the safe form.
_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
  _dir="$(cd -P "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ "$_src" != /* ]] && _src="$_dir/$_src"
done
HSRC="$(cd -P "$(dirname "$_src")" && pwd)"
unset _src _dir
HELPER="${HSRC}/_helpers/wip_limit_check.py"
if [[ -f "$HELPER" ]]; then
  python3 "$HELPER" "$payload"
else
  exit 0
fi

exit_code=$?
cos_log_hook "enforce-wip-limit" "$([[ $exit_code -eq 0 ]] && echo allow || echo block)" 2>/dev/null || true
exit $exit_code
