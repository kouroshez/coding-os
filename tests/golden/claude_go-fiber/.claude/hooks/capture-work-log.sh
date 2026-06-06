#!/usr/bin/env bash
# PostToolUse: after Write/Edit on code files when .task-current is set
# Appends ONE line to the active task's Work Log with `flock` serialization
# for multi-agent safety (R-L-26, R-L-3).
#
# Claude-only: Codex sessions lack PostToolUse delivery — they must call
# cos_work_log_append() explicitly (see AGENTS.md fragment).
#
# Fire-and-forget: never blocks, fail-soft on any error.

set -eu  # NOT -o pipefail — we want to tolerate soft failures.
source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi


cos_log_hook "capture-work-log" "entry" 2>/dev/null || true

# Only care about Edit/Write on code files.
payload="$(cos_read_stdin_bounded 5)"
tool_name="$(echo "$payload" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("tool_name", ""))
except Exception:
    print("")
' 2>/dev/null || echo "")"

case "$tool_name" in
    Edit|Write|MultiEdit) ;;
    *) exit 0 ;;
esac

# Resolve active task.
task_current_file="${COS_PANEL_DIR:-${COS_AGENT_DIR:-.coding-os/claude}}/.task-current"  # panel-first: .task-current is per-panel
[[ -f "$task_current_file" ]] || exit 0
task_current="$(tr -d ' \n' < "$task_current_file" 2>/dev/null)"
[[ -n "$task_current" ]] || exit 0

# Extract TASK-NNN if the marker contains one, else skip (marker may be
# a slug like "phase-l-implementation" which doesn't map to a task file).
task_id="$(echo "$task_current" | grep -oE 'TASK-[0-9]+' | head -1 || true)"
[[ -n "$task_id" ]] || exit 0

# Derive summary from the tool call.
summary="$(echo "$payload" | python3 -c '
import json, os, sys
try:
    d = json.load(sys.stdin)
    ti = d.get("tool_input", {})
    fp = ti.get("file_path", "")
    desc = ti.get("description") or ""
    # Prefer description if set; else synthesize.
    if desc:
        out = f"{desc[:80]} ({os.path.basename(fp)})"
    else:
        out = f"Edit {os.path.basename(fp)}"
    print(out[:120])
except Exception:
    print("")
' 2>/dev/null || echo "")"
[[ -n "$summary" ]] || exit 0

# Serialize via flock on per-agent lock.
lock_dir="${COS_AGENT_DIR:-.coding-os/claude}/locks"
mkdir -p "$lock_dir" 2>/dev/null || exit 0
lock_file="$lock_dir/${task_id}.lock"

# Background fire-and-forget. bash 5.3.9 deadlocks `python3 - <<HEREDOC`;
# extracted to _helpers/work_log_append.py. task_id and summary pass via
# argv (avoids triple-quote escaping fragility too).
_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
  _dir="$(cd -P "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ "$_src" != /* ]] && _src="$_dir/$_src"
done
HSRC="$(cd -P "$(dirname "$_src")" && pwd)"
unset _src _dir
HELPER="${HSRC}/_helpers/work_log_append.py"
if [[ -f "$HELPER" ]]; then
  (
    exec 9>"$lock_file"
    if flock -w 2 9; then
      COS_PROJECT_ROOT="${COS_PROJECT_ROOT:-$PWD}" \
        python3 "$HELPER" "$task_id" "$summary" >/dev/null 2>&1
    fi
  ) &
fi

cos_log_hook "capture-work-log" "spawned" 2>/dev/null || true

# Visible signal — record per-turn activity (rendered by next pulse) +
# emit systemMessage for future agent renderers / SDK consumers.
cos_record_activity worklog "+1 ${task_id}" 2>/dev/null || true
printf '%s' "{\"systemMessage\":\"[worklog] +1 ${task_id}\"}"

exit 0
