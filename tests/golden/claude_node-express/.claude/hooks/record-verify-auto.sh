#!/usr/bin/env bash
# record-verify-auto.sh (PostToolUse Bash) — auto-record suite results.
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

# `unknown`, never 0. An absent exit_code means the runtime did not say how the
# suite ended, and the ledger this writes is what `enforce-verify.sh` reads to
# let `cos task-done` through — so a defaulted 0 turns "no information" into a
# green light. Measured before this: a payload whose stdout read "1 failed,
# 2 passed" and carried no exit_code was ledgered PASS, byte-identical to a
# real pass.
EXIT_CODE=$(echo "$INPUT" | jq -r '.tool_response.exit_code // .tool_response.exitCode // "unknown"' 2>/dev/null || echo unknown)
EVENT_NAME=$(echo "$INPUT" | jq -r '.hook_event_name // empty' 2>/dev/null || echo "")

# Captured from a live Claude Code run, because this contract is not documented
# anywhere and guessing it is what produced the phantom PASS:
#   success -> PostToolUse,        tool_response = {stdout, stderr, interrupted,
#                                   isImage, noOutputExpected}   (no exit_code)
#   failure -> PostToolUseFailure, tool_response absent, top-level `error` set
# So the EVENT is the outcome here, and a PostToolUse carrying a tool_response
# object is a genuine success signal rather than a missing one. A runtime that
# sends neither an exit_code nor a failure event still falls through to
# `unknown` below and records nothing.
if [[ "$EVENT_NAME" == "PostToolUseFailure" ]]; then
  EXIT_CODE=1
elif [[ "$EXIT_CODE" == "unknown" && "$EVENT_NAME" == "PostToolUse" ]]; then
  HAS_RESPONSE=$(echo "$INPUT" | jq -r 'if (.tool_response | type) == "object" then "yes" else "no" end' 2>/dev/null || echo no)
  HAS_ERROR=$(echo "$INPUT" | jq -r 'if (.error // null) == null then "no" else "yes" end' 2>/dev/null || echo no)
  if [[ "$HAS_RESPONSE" == "yes" && "$HAS_ERROR" == "no" ]]; then
    EXIT_CODE=0
  fi
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

# Record nothing rather than a guess. Skipping costs one re-run; a phantom PASS
# costs a suite nobody notices was red.
if [[ "$EXIT_CODE" == "unknown" ]]; then
  cos_log_hook record-verify-auto skipped "suite=$SUITE reason=no-exit-code-in-payload" 2>/dev/null || true
  exit 0
fi

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
