#!/usr/bin/env bash
# warn-destructive-edit.sh
# PreToolUse Write|Edit|MultiEdit — friction before destruction: warn (strict = block)
# before a large net-deletion/overwrite of a load-bearing file, pointing at the git
# command to see what was there. Self-throttling + fail-open. Spec:
# docs/engineering/destructive-edit-guard.md
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

# Default-on at "warn". Opt-out: COS_DESTRUCTIVE_GUARD=off. Stricter: =strict (block on hit).
MODE="${COS_DESTRUCTIVE_GUARD:-1}"
if [[ "$MODE" == "off" || "$MODE" == "0" ]]; then
  cos_log_hook warn-destructive-edit disabled || true
  exit 0
fi

INPUT="$(cos_read_stdin_bounded 2 2>/dev/null || true)"
if [[ -z "$INPUT" ]]; then
  cos_log_hook warn-destructive-edit no-input || true
  exit 0
fi

CONFIG="${COS_STATE_DIR:-.coding-os}/rag-config.yaml"
[[ -f "$CONFIG" ]] || CONFIG="$(pwd)/.coding-os/rag-config.yaml"

# Resolve the real hook dir (symlink-safe) to find the helper — same idiom as enforce-graph-context.
_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
  _dir="$(cd -P "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ "$_src" != /* ]] && _src="$_dir/$_src"
done
HSRC="$(cd -P "$(dirname "$_src")" && pwd)"
unset _src _dir
HELPER="${HSRC}/_helpers/destructive_edit_check.py"
if [[ ! -f "$HELPER" ]]; then
  cos_log_hook warn-destructive-edit no-helper || true
  exit 0
fi

VERDICT="$(printf '%s' "$INPUT" | python3 "$HELPER" "$CONFIG" 2>/dev/null || true)"
if [[ -z "$VERDICT" ]]; then
  cos_log_hook warn-destructive-edit no-verdict || true
  exit 0
fi

FLAGGED="$(printf '%s' "$VERDICT" | cos_json_field flagged)"
FLAGGED="${FLAGGED:-false}"
if [[ "$FLAGGED" != "true" ]]; then
  cos_log_hook warn-destructive-edit ok || true
  exit 0
fi

MSG="$(printf '%s' "$VERDICT" | cos_json_field message)"
if [[ "$MODE" == "strict" ]]; then
  printf 'BLOCKED: %s\n' "$MSG" >&2
  printf '  to proceed: split the deletion into a separate reviewed change, or set COS_DESTRUCTIVE_GUARD=warn.\n' >&2
  cos_log_hook warn-destructive-edit block || true
  exit 2
fi
printf 'warning: %s\n' "$MSG" >&2
cos_log_hook warn-destructive-edit warn || true
exit 0
