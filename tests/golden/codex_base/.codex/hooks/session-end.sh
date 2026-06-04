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
_TASK_CURRENT="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.task-current"  # panel-first (TASK-035)
if [ -f "$_TASK_CURRENT" ]; then
  ACTIVE_TASK=$(grep -oE 'TASK-[0-9]+' "$_TASK_CURRENT" 2>/dev/null | head -1 || true)
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

# Phase EVO — auto-trajectory: derive trajectory snapshot from this session's
# formula_dispatches + backtrack_events → future sessions inherit project intent.
AUTOSNAP_PY="${_COS_HOOKS_PHYS}/_helpers/trajectory_autosnap.py"
if [ -f "$AUTOSNAP_PY" ]; then
  run_bounded_python "$AUTOSNAP_PY" 2
fi

# Responsive learning — extract patterns same-day once enough new task_outcomes
# accrue (scheduled config threshold) instead of waiting for the nightly cron.
# Shares the .last-extract marker with nightly.py so the paths stay idempotent.
RESPONSIVE_PY="${_COS_HOOKS_PHYS}/../scheduled/responsive_extract.py"
if [ -f "$RESPONSIVE_PY" ]; then
  run_bounded_python "$RESPONSIVE_PY" 3
fi

# End-of-turn visible recap — Stop hooks accept hookSpecificOutput JSON, which
# Claude Code surfaces as a labeled additionalContext block between turns.
# Mirrors the always-on caveman pattern so the operator never sees a silent
# session boundary. Bounded fire-and-forget — never blocks.
RECAP_PY="${_COS_HOOKS_PHYS}/_helpers/session_recap.py"
if [ -f "$RECAP_PY" ] && [ -f "$COS_DB_PATH" ] && [ -n "$SESSION_ID" ]; then
  python3 "$RECAP_PY" "$COS_DB_PATH" "$SESSION_ID" 2>/dev/null || true
fi
