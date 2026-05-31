#!/usr/bin/env bash
# PreToolUse hook: BLOCK task-done commands unless domain-appropriate
# verification has been run recently.
#
# Phase L.10 / TASK-100 — data-driven via src/core/board_os/verify-suites.yaml.
# No more hardcoded customer paths (frontend/app/*/checkout/* etc.).
# Consumer projects extend by writing their own
# .coding-os/verify-suites.yaml.
#
# Catches all three "complete this task" entry points:
#   make task-done … · cos task-done … · cos task-move … --to complete
#
# Override (audited): COS_VERIFY_OVERRIDE=1 COS_OVERRIDE_REASON="...≥15 chars"
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi


INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")

if [[ "$TOOL" != "Bash" ]]; then
  exit 0
fi

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")

# Match only commands that ACTUALLY run task-done — anchor on the start
# of a logical command (^ or after `&&`/`;`/`|`/`(`) so the regex does not
# fire on commit messages or scripts that mention these strings as text.
# Three forms: `make task-done…`, `cos task-done…`, `cos task-move … --to complete`.
FIRST_TOKEN_OF_EACH=$(echo "$COMMAND" | tr ';&|()' '\n' | awk '{$1=$1};1' | grep -v '^$' | head -20)
IS_TASK_DONE=false
while IFS= read -r segment; do
  case "$segment" in
    "make "*"task-done"*)              IS_TASK_DONE=true ;;
    "cos task-done"*)                  IS_TASK_DONE=true ;;
    "cos task-move"*"--to complete"*)  IS_TASK_DONE=true ;;
    "cos task-move"*"--to=complete"*)  IS_TASK_DONE=true ;;
  esac
done <<< "$FIRST_TOKEN_OF_EACH"

if ! $IS_TASK_DONE; then
  # Silent skip — logging [fire] for every Bash floods .hooks.log with
  # noise the operator cannot act on. The hook only matters when the
  # command IS task-done; non-matches are uninteresting.
  exit 0
fi

cos_log_hook enforce-verify fire "tool=Bash task_done=true"

# ── Resolve required suites via Python (data-driven) ────────────────
PROJECT_ROOT="${COS_PROJECT_ROOT:-$(pwd)}"
cd "$PROJECT_ROOT" || exit 0

CHANGED_FILES=$(git diff --name-only HEAD 2>/dev/null || true)
if [[ -z "$CHANGED_FILES" ]]; then
  exit 0
fi

if command -v uv >/dev/null 2>&1; then
  PYRUN=(uv run --quiet python)
else
  PYRUN=(python3)
fi

# Resolve suites + check freshness in one Python call so we avoid the
# per-suite subprocess thrash the legacy script had. The CLI prints
# either "OK" or a multi-line block report on stderr.
set +e
echo "$CHANGED_FILES" | "${PYRUN[@]}" -m core.board_os.verify_suites_cli check \
  --verify-file "${COS_STATE_DIR}/.last-verify.json"
EXIT_CODE=$?
set -e

cos_log_hook enforce-verify "$([[ $EXIT_CODE -eq 0 ]] && echo allow || echo block)" \
  "reason=domain-suites" 2>/dev/null || true
exit "$EXIT_CODE"
