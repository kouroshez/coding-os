#!/usr/bin/env bash
# link-commit-to-task.sh (PostToolUse Bash) — after a real `git commit`, append
# the new HEAD sha + subject to the active task's Work Log, so cos_task_history
# surfaces the CODE commits, not just the commits that touched the task .md
# (TASK-273). cos_task_history::_git_commits_from_worklog greps the work log for
# 7-40 hex SHAs and links them, so recording the sha here is the whole contract.
#
# Fire-and-forget: dedups by sha, fail-open (exit 0) on any error, never blocks.
# Claude-only in practice (Codex lacks reliable PostToolUse delivery; it records
# commits via cos_work_log_append explicitly).
set -eu  # NOT -o pipefail — tolerate soft failures.
source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook "link-commit-to-task" "entry" 2>/dev/null || true

payload="$(cos_read_stdin_bounded 5)"

# Fast-path: this hook fires on EVERY Bash command, so the common (non-commit)
# case must cost a single string match, not two python3 spawns. If the raw
# payload doesn't even mention a commit, bail before parsing.
case "$payload" in
    *"git commit"*) ;;
    *) exit 0 ;;
esac

# Parse tool_name + command once. Only a real `git commit` on the Bash tool.
mapfile -t _parsed < <(echo "$payload" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    ti = d.get("tool_input", {}) or {}
    print(d.get("tool_name", ""))
    print((ti.get("command", "") or "").replace("\n", " "))
except Exception:
    print(""); print("")
' 2>/dev/null)
tool_name="${_parsed[0]:-}"
command="${_parsed[1]:-}"

[[ "$tool_name" == "Bash" ]] || exit 0
case "$command" in
    *"git commit"*) ;;
    *) exit 0 ;;
esac
# A dry-run / help invocation creates no commit — don't link the prior HEAD.
case "$command" in
    *--dry-run*|*--help*) exit 0 ;;
esac

# Resolve active task (panel-first: .task-current is per-panel).
task_current_file="${COS_PANEL_DIR:-${COS_AGENT_DIR:-.coding-os/claude}}/.task-current"
[[ -f "$task_current_file" ]] || exit 0
task_current="$(tr -d ' \n' < "$task_current_file" 2>/dev/null)"
task_id="$(echo "$task_current" | grep -oE 'TASK-[0-9]+' | head -1 || true)"
[[ -n "$task_id" ]] || exit 0

# New HEAD after the commit ran (PostToolUse fires post-command).
root="${COS_PROJECT_ROOT:-$PWD}"
sha="$(git -C "$root" rev-parse --short=10 HEAD 2>/dev/null || true)"
[[ -n "$sha" ]] || exit 0
subject="$(git -C "$root" log -1 --format=%s 2>/dev/null || true)"

# Dedup: skip when this commit is already in the task's Work Log. Match a
# 7-char prefix so an entry the git post-commit hook (TASK-175) wrote with a
# shorter `--short` sha is still recognised — avoids a double link.
task_file="$(ls "$root"/docs/tasks/"${task_id}"-*.md 2>/dev/null | head -1 || true)"
if [[ -n "$task_file" ]] && grep -q "${sha:0:7}" "$task_file" 2>/dev/null; then
    exit 0
fi

summary="commit ${sha} — ${subject}"
summary="${summary:0:120}"

# Serialize via flock on per-agent lock (mirrors capture-work-log.sh).
lock_dir="${COS_AGENT_DIR:-.coding-os/claude}/locks"
mkdir -p "$lock_dir" 2>/dev/null || exit 0
lock_file="$lock_dir/${task_id}.lock"

# bash 5.3.9 deadlocks `python3 - <<HEREDOC`; reuse _helpers/work_log_append.py.
_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
    _dir="$(cd -P "$(dirname "$_src")" && pwd)"
    _src="$(readlink "$_src")"
    [[ "$_src" != /* ]] && _src="$_dir/$_src"
done
HSRC="$(cd -P "$(dirname "$_src")" && pwd)"
unset _src _dir
# COS_WORKLOG_HELPER override keeps the append mechanism stubbable in tests
# (same seam as the git post-commit body, src/scripts/_post_commit_body.sh).
HELPER="${COS_WORKLOG_HELPER:-${HSRC}/_helpers/work_log_append.py}"
if [[ -f "$HELPER" ]]; then
    (
        exec 9>"$lock_file"
        if flock -w 2 9; then
            COS_PROJECT_ROOT="${COS_PROJECT_ROOT:-$PWD}" \
                python3 "$HELPER" "$task_id" "$summary" >/dev/null 2>&1
        fi
    ) &
fi

cos_log_hook "link-commit-to-task" "linked ${sha}" 2>/dev/null || true
cos_record_activity worklog "commit ${sha} ${task_id}" 2>/dev/null || true
printf '%s' "{\"systemMessage\":\"[worklog] commit ${sha} → ${task_id}\"}"

exit 0
