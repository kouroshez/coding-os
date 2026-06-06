#!/usr/bin/env bash
# Codex Stop dispatcher: sequence end-of-session hooks without invalid stdout.
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$HOOK_DIR/cos-env.sh" 2>/dev/null || source "$HOOK_DIR/../../../core/hooks/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then
  cos_log_hook() { :; }
fi

INPUT=$(cat)
cos_log_hook codex-stop-dispatch fire

delegate_path() {
  local delegate="$1"
  if [[ -f "$HOOK_DIR/$delegate" ]]; then
    echo "$HOOK_DIR/$delegate"
  else
    echo "$HOOK_DIR/../../../core/hooks/$delegate"
  fi
}

run_delegate() {
  local delegate="$1"
  local stdout_file stderr_file rc
  stdout_file=$(mktemp "${TMPDIR:-/tmp}/codex-stop-out.XXXXXX")
  stderr_file=$(mktemp "${TMPDIR:-/tmp}/codex-stop-err.XXXXXX")

  set +e
  bash "$(delegate_path "$delegate")" <<< "$INPUT" >"$stdout_file" 2>"$stderr_file"
  rc=$?
  set -e

  if [[ "$rc" -eq 0 ]]; then
    if [[ -s "$stdout_file" ]]; then
      cos_log_hook codex-stop-dispatch warn "delegate=${delegate} dropped_stdout=true"
    fi
    if [[ -s "$stderr_file" ]]; then
      cat "$stderr_file" >&2
    fi
    rm -f "$stdout_file" "$stderr_file"
    return 0
  fi
  if [[ -s "$stderr_file" ]]; then
    cat "$stderr_file" >&2
  fi
  if [[ "$rc" -eq 2 ]]; then
    cos_log_hook codex-stop-dispatch block "delegate=${delegate}"
    rm -f "$stdout_file" "$stderr_file"
    exit 2
  fi

  cos_log_hook codex-stop-dispatch warn "delegate=${delegate} rc=${rc}"
  rm -f "$stdout_file" "$stderr_file"
  return 0
}

# Set MUST match adapter.yaml::hook_dispatchers[Stop].delegates (asserted by
# tests/test_adapter_parity.py). verify-completion-claim +
# prevent-premature-done are intentionally ABSENT: they emit their effect via
# exit-0 stdout JSON ({"decision":"block"} / additionalContext) which this
# dispatcher drops, so wiring them would be silent no-ops. Forwarding that
# stdout is its own scoped task — until then they stay Claude-only.
for delegate in session-end.sh warn-abandoned-task.sh check-capture-worked.sh auto-trace-rotate.sh snapshot-transcript.sh agent-presence.sh; do
  run_delegate "$delegate"
done

# Stop hooks in Codex currently expect JSON on stdout when exiting 0.
# An empty object means "success, no continuation requested".
printf '{}\n'

exit 0
