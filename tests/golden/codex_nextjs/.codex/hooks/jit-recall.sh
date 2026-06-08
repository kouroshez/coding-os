#!/usr/bin/env bash
# jit-recall.sh (Phase O) — PreToolUse Write|Edit just-in-time recall (B2).
#
# Right before an edit, surface a past friction lesson about THIS file (lesson
# text contains the basename) so the agent avoids a repeat mistake at the moment
# it matters. Warn-only (exit 0, stderr — same surfacing as enforce-graph-context),
# debounced once per (file, session). Fail-open: never blocks a tool call.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
[[ -z "$FILE_PATH" ]] && exit 0

# Debounce once per (file, session) — only set the marker when we actually surface.
FILE_HASH=$(printf '%s' "$FILE_PATH" | shasum 2>/dev/null | cut -c1-12 || echo "nohash")
MARKER="${COS_PANEL_DIR:-${COS_AGENT_DIR:-.coding-os}}/.jit-recall-${FILE_HASH}"
[[ -f "$MARKER" ]] && exit 0

DB="${COS_DB_PATH:-${COS_STATE_DIR:-.coding-os}/coding-os.db}"
[[ -f "$DB" ]] || exit 0

LESSON="$(python3 "$(dirname "$0")/_helpers/jit_recall.py" "$DB" "$FILE_PATH" 2>/dev/null || true)"
if [[ -n "$LESSON" ]]; then
  : > "$MARKER" 2>/dev/null || true
  printf 'warning: 🧠 [recall] past lesson for this file — %s\n' "$LESSON" >&2
  cos_log_hook jit-recall warn || true
  exit 0
fi
cos_log_hook jit-recall ok || true
exit 0
