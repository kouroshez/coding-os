#!/usr/bin/env bash
# PostToolUse Write|Edit — reuse-first placement nudge (non-blocking).
#
# When an edit under src/services/<svc>/ defines a symbol that is also defined
# in a different same-language service, suggest promoting it to
# src/shared/<lang>/ (project-anatomy.md). Advisory only: always exits 0.
# Debounced per panel+file. Real logic lives in _nudge_reuse_first.py (Rule 8).
# Fail-open by design: any missing dep / parser error → silent skip.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi


INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

PROJECT_ROOT="${COS_PROJECT_ROOT:-$PWD}"
case "$FILE_PATH" in
  "${PROJECT_ROOT}/"*) REL_PATH="${FILE_PATH#${PROJECT_ROOT}/}" ;;
  *)                   REL_PATH="$FILE_PATH" ;;
esac

# Only cross-service edits can duplicate a symbol across services — fast-path
# out of every other write so the hook adds no cost to the common case.
case "$REL_PATH" in
  src/services/*) ;;
  *) exit 0 ;;
esac

# Debounce per panel+file: one nudge per file per window (avoids re-nudging on
# rapid successive edits of the same file).
_DEBOUNCE_TTL=120
_STATE_BASE="${COS_PANEL_DIR:-${COS_STATE_DIR:-${PROJECT_ROOT}/.coding-os}}"
_SAFE_PATH=$(printf '%s' "$REL_PATH" | tr '/ .' '_')
_DEBOUNCE_FILE="${_STATE_BASE}/.reuse-nudge-${_SAFE_PATH}"
_NOW=$(date +%s)
if [[ -f "$_DEBOUNCE_FILE" ]]; then
  _LAST=$(cat "$_DEBOUNCE_FILE" 2>/dev/null || echo 0)
  if (( _NOW - _LAST < _DEBOUNCE_TTL )); then
    exit 0
  fi
fi
mkdir -p "$(dirname "$_DEBOUNCE_FILE")" 2>/dev/null || true
echo "$_NOW" > "$_DEBOUNCE_FILE" 2>/dev/null || true

PY_DELEGATE="$(dirname "$0")/_nudge_reuse_first.py"
if [[ ! -f "$PY_DELEGATE" ]]; then
  exit 0
fi

cos_log_hook nudge-reuse-first fire "file=${REL_PATH}"
OUTPUT="$("${COS_PYTHON:-python3}" "$PY_DELEGATE" "$REL_PATH" "$PROJECT_ROOT" 2>/dev/null || true)"

if [[ -n "$OUTPUT" ]]; then
  echo "$OUTPUT" >&2
  cos_log_hook nudge-reuse-first nudge "file=${REL_PATH}"
fi

exit 0
