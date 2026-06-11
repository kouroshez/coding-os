#!/usr/bin/env bash
# capture-audit.sh (PostToolUse Write|Edit) — auto doc-audit-log capture.
#
# For Write/Edit/MultiEdit on docs/** files, appends an immutable
# doc_audit_trail row via ../thinking_os/capture_audit.py (which calls
# audit_log_record). Symmetry with capture-observation.sh: the MCP tool
# cos_audit_log_record stays the manual / Codex path; this is the auto path.
# Pre-filters to docs/** in shell so non-doc edits never spawn python.
# Fire-and-forget: errors -> $COS_STATE_DIR/.audit-capture-errors.log, exit 0.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null || echo "")
case "$TOOL_NAME" in
  Write|Edit|MultiEdit) ;;
  *) exit 0 ;;
esac

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
# Only documentation files — cheap pre-filter before any python spawn.
case "$FILE_PATH" in
  docs/*|*/docs/*) ;;
  *) exit 0 ;;
esac

cos_log_hook capture-audit fire "tool=${TOOL_NAME}"

# Resolve through the .claude/hooks symlink to reach ../thinking_os/.
_src="${BASH_SOURCE[0]:-$0}"
while [ -L "$_src" ]; do
  _dir="$(cd -P "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ "$_src" != /* ]] && _src="$_dir/$_src"
done
HOOK_REAL_DIR="$(cd -P "$(dirname "$_src")" && pwd)"
unset _src _dir
CAPTURE_PY="${HOOK_REAL_DIR}/../thinking_os/capture_audit.py"
[ -f "$CAPTURE_PY" ] || { cos_log_hook capture-audit skip "reason=helper_missing" 2>/dev/null || true; exit 0; }

COS_STATE_DIR="${COS_STATE_DIR:-.coding-os}"
mkdir -p "$COS_STATE_DIR" 2>/dev/null || true
echo "$INPUT" | python3 "$CAPTURE_PY" 2>>"$COS_STATE_DIR/.audit-capture-errors.log" || true

exit 0
