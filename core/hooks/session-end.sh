#!/usr/bin/env bash
# Stop hook: Record enriched session summary to coding-os.db.
# Agent-agnostic: uses COS_STATE_DIR and COS_DB_PATH.
# Fire-and-forget — never blocks or errors visibly.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

# Resolve physical hooks dir for symlink-safe thinking_os lookup.
_cos_src="${BASH_SOURCE[0]}"
while [ -L "$_cos_src" ]; do
  _cos_dir="$(cd -P "$(dirname "$_cos_src")" && pwd)"
  _cos_src="$(readlink "$_cos_src")"
  [[ "$_cos_src" != /* ]] && _cos_src="${_cos_dir}/${_cos_src}"
done
_COS_HOOKS_PHYS="$(cd -P "$(dirname "$_cos_src")" && pwd)"
unset _cos_src _cos_dir

SESSION_ID=""
if [ -f "$COS_SESSION_FILE" ]; then
  SESSION_ID=$(cat "$COS_SESSION_FILE")
fi
# No extra `session=` in the detail — cos_log_hook already emits the
# identity triplet (agent=X session=Y task=Z) in the standard prefix.
cos_log_hook session-end fire

if [ ! -f "$COS_DB_PATH" ]; then
  exit 0
fi

ACTIVE_TASK=""
if [ -f "docs/tasks.md" ]; then
  ACTIVE_TASK=$(grep '^\- \[/\]' docs/tasks.md | head -1 | grep -oE 'TASK-[0-9]+' || true)
fi

run_bounded_python() {
  local script="$1"
  local timeout_s="${2:-2}"
  python3 -c '
import subprocess
import sys

script, timeout_s, *args = sys.argv[1:]
try:
    subprocess.run(
        [sys.executable, script, *args],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=float(timeout_s),
        check=False,
    )
except Exception:
    pass
' "$script" "$timeout_s" "$SESSION_ID" "$ACTIVE_TASK" "$COS_DB_PATH" >/dev/null 2>&1 || true
}

# Find scripts in coding-os core — physical path resolves symlinked installs.
SUMMARY_PY="${_COS_HOOKS_PHYS}/../thinking_os/session_summary.py"
if [ -f "$SUMMARY_PY" ]; then
  run_bounded_python "$SUMMARY_PY" 2
fi

ENRICH_PY="${_COS_HOOKS_PHYS}/../thinking_os/session_enrich.py"
if [ -f "$ENRICH_PY" ]; then
  run_bounded_python "$ENRICH_PY" 2
fi
