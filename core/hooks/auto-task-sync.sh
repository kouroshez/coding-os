#!/usr/bin/env bash
# Phase L.4 — PostToolUse: Write/Edit on docs/tasks/*.md
# Re-syncs the single file into the DB cache so the board is fresh
# within one hook latency (<200ms per §8.2).
#
# Fail-soft: background subprocess; never blocks the tool response.

set -eu
source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

cos_log_hook "auto-task-sync" "entry" 2>/dev/null || true

payload="$(cos_read_stdin_bounded 5)"
file_path="$(echo "$payload" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))
except Exception:
    print("")
' 2>/dev/null || echo "")"

if [[ "$file_path" != *"docs/tasks/"*.md ]]; then
    exit 0
fi

# Background, fire-and-forget. bash 5.3.9 deadlocks `python3 - <<HEREDOC`
# — extracted to _helpers/task_sync.py.
_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
  _dir="$(cd -P "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ "$_src" != /* ]] && _src="$_dir/$_src"
done
HSRC="$(cd -P "$(dirname "$_src")" && pwd)"
unset _src _dir
HELPER="${HSRC}/_helpers/task_sync.py"
if [[ -f "$HELPER" ]]; then
  (
    COS_PROJECT_ROOT="${COS_PROJECT_ROOT:-$PWD}" \
      python3 "$HELPER" "$file_path" >/dev/null 2>&1
  ) &
fi

cos_log_hook "auto-task-sync" "spawned" 2>/dev/null || true
exit 0
