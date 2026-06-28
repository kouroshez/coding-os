#!/usr/bin/env bash
# record-verify-auto.sh (PostToolUse Bash) — auto-record suite results (TASK-329).
#
# When a Bash command that executes a verify suite (data-driven match against
# verify-suites.yaml via `verify_suites_cli match-command`) completes, record
# PASS/FAIL + commit keys to $COS_STATE_DIR/.last-verify.json through
# record-verify.sh, and clear the test-run lockfile the test-governor wrote.
# Observation phase: fail-open, always exit 0.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"

# Fast-path: this recorder only acts on verify-suite commands. If the raw
# payload mentions none of the suite verbs there is nothing to record — bail
# before any jq spawn (fires on EVERY Bash tool call). The precise COMMAND-
# level case below still gates the actual work.
case "$INPUT" in
  *pytest*|*"make verify-hooks"*|*"make docs-lint"*|*"make ui-test"*) ;;
  *) exit 0 ;;
esac

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")
[[ -n "$COMMAND" ]] || exit 0

# Cheap pre-filter — only suite-shaped commands reach the python matcher.
case "$COMMAND" in
  *pytest*|*"make verify-hooks"*|*"make docs-lint"*|*"make ui-test"*) ;;
  *) exit 0 ;;
esac
case "$COMMAND" in
  *--collect-only*|*" --co"*) exit 0 ;;
esac

EXIT_CODE=$(echo "$INPUT" | jq -r '.tool_response.exit_code // .tool_response.exitCode // 0' 2>/dev/null || echo 0)
# TASK-335: on PostToolUseFailure the payload may carry no exit_code at all —
# the event itself IS the failure signal; never let the `// 0` default record
# a phantom PASS.
EVENT_NAME=$(echo "$INPUT" | jq -r '.hook_event_name // empty' 2>/dev/null || echo "")
if [[ "$EVENT_NAME" == "PostToolUseFailure" ]]; then
  EXIT_CODE=1
fi

PROJECT_ROOT="${COS_PROJECT_ROOT:-$(pwd)}"
if command -v uv >/dev/null 2>&1; then
  PYRUN=(uv run --quiet python)
else
  PYRUN=(python3)
fi
MATCH=$(cd "$PROJECT_ROOT" && "${PYRUN[@]}" -m core.board_os.verify_suites_cli match-command --command "$COMMAND" 2>/dev/null) || MATCH='{}'
SUITE=$(echo "$MATCH" | jq -r '.suite // empty' 2>/dev/null || echo "")
IS_PYTEST=$(echo "$MATCH" | jq -r '.pytest_invocation // false' 2>/dev/null || echo false)

# A completed pytest run frees the host — clear the governor's lockfile.
# Commands that merely MENTION pytest (echo/heredoc payloads) must NOT
# clear a sibling session's live lock.
if [[ "$IS_PYTEST" == "true" ]]; then
  rm -f "${COS_STATE_DIR}/.test-run.lock" 2>/dev/null || true
fi

[[ -n "$SUITE" ]] || exit 0

STATUS="PASS"
[[ "$EXIT_CODE" == "0" ]] || STATUS="FAIL"

bash "$(dirname "$0")/record-verify.sh" "$SUITE" "$STATUS" >/dev/null 2>&1 || true
cos_log_hook record-verify-auto recorded "suite=$SUITE status=$STATUS" 2>/dev/null || true

# F-TST-3: a matrix-suite FAIL must be QUERYABLE (it reached only the hook jsonl
# before). cos_say at ERROR routes through cos_say_json.py into the log_events
# sink (DB floor WARN), so `cos_log_query` / an auto-bug-filer can surface it.
if [[ "$STATUS" == "FAIL" ]] && command -v cos_say >/dev/null 2>&1; then
  cos_say ERROR "verify.${SUITE}" "matrix suite failed (exit ${EXIT_CODE})" 2>/dev/null || true
fi
exit 0
