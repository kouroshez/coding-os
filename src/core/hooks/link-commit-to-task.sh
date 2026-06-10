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

# Parse tool_name + command + the sha THIS command minted, in one spawn.
# The sha comes from the git output line "[branch abc1234] subject" inside
# tool_response — never from a bare rev-parse HEAD: under concurrent
# sessions HEAD is whoever committed last, and the old HEAD read cross-
# linked sibling sessions' commits (TASK-340 repro, 2026-06-10 15:59).
mapfile -t _parsed < <(echo "$payload" | python3 -c '
import json, re, sys
try:
    d = json.load(sys.stdin)
    ti = d.get("tool_input", {}) or {}
    tr = d.get("tool_response", "") or ""
    if isinstance(tr, dict):
        out = " ".join(str(tr.get(k, "") or "") for k in ("stdout", "output", "stderr"))
    else:
        out = str(tr)
    m = re.search(r"\[[^]\n]+ ([0-9a-f]{7,40})\]", out)
    print(d.get("tool_name", ""))
    print((ti.get("command", "") or "").replace("\n", " "))
    print(m.group(1) if m else "")
except Exception:
    print(""); print(""); print("")
' 2>/dev/null)
tool_name="${_parsed[0]:-}"
command="${_parsed[1]:-}"
sha="${_parsed[2]:-}"

[[ "$tool_name" == "Bash" ]] || exit 0
case "$command" in
    *"git commit"*) ;;
    *) exit 0 ;;
esac
# A dry-run / help invocation creates no commit — don't link the prior HEAD.
case "$command" in
    *--dry-run*|*--help*) exit 0 ;;
esac

# Upgrade panel resolution from the payload's session_id — env-derived
# COS_PANEL_DIR can be a ppid-* fallback that misses this panel's state.
cos_panel_upgrade_from_payload "$payload" 2>/dev/null || true

# Resolve active task (panel-first: .task-current is per-panel) and verify
# OWNERSHIP: write-state.sh stamps "<session-id> <value>"; a marker stamped
# by a different session is another panel's fossil — linking to it would
# attribute this commit to a task this session never started.
task_current_file="${COS_PANEL_DIR:-${COS_AGENT_DIR:-.coding-os/claude}}/.task-current"
[[ -f "$task_current_file" ]] || exit 0
task_line="$(head -n 1 "$task_current_file" 2>/dev/null || true)"
owner="${task_line%% *}"
case "$owner" in
    ses-*|ppid-*)
        current_session="$(cos_current_session 2>/dev/null || true)"
        [[ -n "$current_session" && "$owner" == "$current_session" ]] || exit 0
        ;;
esac
task_id="$(echo "$task_line" | grep -oE 'TASK-([A-Z][A-Z0-9]*-)?[0-9]+' | head -1 || true)"
[[ -n "$task_id" ]] || exit 0

root="${COS_PROJECT_ROOT:-$PWD}"
if [[ -z "$sha" ]]; then
    # Output was piped/filtered (e.g. `git commit … | tail -1`) so the
    # "[branch sha]" line is gone. Safe fallback: the single commit minted
    # in the last 20s. Two or more candidates = a sibling session is also
    # committing — skip rather than guess (a missing link beats a wrong one).
    mapfile -t _recent < <(git -C "$root" log --format='%h' --since='20 seconds ago' -n 2 2>/dev/null || true)
    [[ ${#_recent[@]} -eq 1 && -n "${_recent[0]:-}" ]] || exit 0
    sha="${_recent[0]}"
fi
sha="$(git -C "$root" rev-parse --short=10 "$sha" 2>/dev/null || true)"
[[ -n "$sha" ]] || exit 0
subject="$(git -C "$root" log -1 --format=%s "$sha" 2>/dev/null || true)"

# Dedup: skip when this commit is already in the task's Work Log. Match a
# 7-char prefix so an entry the git post-commit hook (TASK-175) wrote with a
# shorter `--short` sha is still recognised — avoids a double link.
task_file="$(ls "$root"/docs/tasks/"${task_id}"-*.md 2>/dev/null | head -1 || true)"
if [[ -n "$task_file" ]] && grep -q "${sha:0:7}" "$task_file" 2>/dev/null; then
    exit 0
fi

summary="commit ${sha} — ${subject}"
summary="${summary:0:120}"

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
# SYNCHRONOUS on purpose: a `… &` here can die with the hook process before
# the append lands — the "linked" log line lied while the Work Log stayed
# empty (TASK-340). Locking lives inside the helper (fcntl — flock(1) does
# not exist on macOS); the append costs ms and commits are infrequent.
HELPER="${COS_WORKLOG_HELPER:-${HSRC}/_helpers/work_log_append.py}"
linked="false"
if [[ -f "$HELPER" ]]; then
    if COS_PROJECT_ROOT="${COS_PROJECT_ROOT:-$PWD}" \
        python3 "$HELPER" "$task_id" "$summary" >/dev/null 2>&1; then
        linked="true"
    fi
fi
if [[ "$linked" != "true" ]]; then
    cos_log_hook "link-commit-to-task" "append-failed ${sha}" 2>/dev/null || true
    exit 0
fi

cos_log_hook "link-commit-to-task" "linked ${sha}" 2>/dev/null || true
cos_record_activity worklog "commit ${sha} ${task_id}" 2>/dev/null || true
printf '%s' "{\"systemMessage\":\"[worklog] commit ${sha} → ${task_id}\"}"

exit 0
