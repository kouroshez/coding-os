#!/usr/bin/env bash
# advance-role.sh (PostToolUse) — advance the active role along the chain.
#
# After a tool runs, move .role to the chain member that matches the current
# work phase (Write/Edit → implementer, test/verify Bash → reviewer) so the
# session banner's roles= field tracks what the agent is DOING, not a frozen
# chain lead.
# Only ever picks a role already IN the composed chain. Fail-open.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2 2>/dev/null || true)"

# Fast-path: this hook only advances the active role when a composed chain
# exists (the .roles marker). No chain → nothing to advance; bail before any
# jq spawn (fires on EVERY Write/Edit/Bash tool call). Check first because it
# is a single stat() vs three jq process spawns.
TARGET_DIR="${COS_PANEL_DIR:-${COS_AGENT_DIR:-${COS_STATE_DIR:-.coding-os}/${COS_AGENT:-claude}}}"
[[ -f "${TARGET_DIR}/.roles" ]] || exit 0

TOOL="$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)"
[[ -n "$TOOL" ]] || exit 0
case "$TOOL" in
  Write|Edit|MultiEdit|Bash) ;;
  *) exit 0 ;;
esac
CMD="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)"
FILE_PATH="$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)"

# Resolve the helper through the hook symlink.
_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
  _dir="$(cd -P "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ "$_src" != /* ]] && _src="$_dir/$_src"
done
HSRC="$(cd -P "$(dirname "$_src")" && pwd)"
HELPER="${HSRC}/_helpers/advance_role.py"
[[ -f "$HELPER" ]] || exit 0

CHOSEN=$(python3 "$HELPER" "$TOOL" "$TARGET_DIR" "$CMD" "$FILE_PATH" 2>/dev/null || true)
if [[ -n "$CHOSEN" ]]; then
  cos_log_hook advance-role ok "tool=${TOOL} role=${CHOSEN}" || true
fi

exit 0
