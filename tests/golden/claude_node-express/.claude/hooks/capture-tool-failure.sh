#!/usr/bin/env bash
# PostToolUseFailure hook: pipe event payload to tool_failure_capture.py.
# Reads session_id from COS_SESSION_FILE and db_path from COS_DB_PATH,
# both exported by cos-env.sh which Claude Code sources via sourced_hooks.
# Fire-and-forget — never blocks or errors visibly.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

SESSION_ID=""
if [[ -f "${COS_SESSION_FILE:-}" ]]; then
  SESSION_ID=$(cat "$COS_SESSION_FILE")
fi

if [[ -z "$SESSION_ID" || -z "${COS_DB_PATH:-}" || ! -f "$COS_DB_PATH" ]]; then
  exit 0
fi

CAPTURE_PY="$(_cos_helpers_dir 2>/dev/null)/tool_failure_capture.py"
if [[ ! -f "$CAPTURE_PY" ]]; then
  exit 0
fi

python3 "$CAPTURE_PY" "$SESSION_ID" "$COS_DB_PATH" || true
