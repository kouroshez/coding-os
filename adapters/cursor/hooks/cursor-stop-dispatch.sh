#!/usr/bin/env bash
# Cursor stop dispatcher: sequence end-of-session hooks; stdout must be JSON.
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$HOOK_DIR/cos-env.sh" 2>/dev/null || source "$HOOK_DIR/../../../core/hooks/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then
  cos_log_hook() { :; }
fi

INPUT=$(cat)
COS_HOOK_RUNTIME_MODEL="$(printf '%s' "$INPUT" | jq -r '.model // empty' 2>/dev/null || true)"
export COS_HOOK_RUNTIME_MODEL
cos_log_hook cursor-stop-dispatch fire

delegate_path() {
  local delegate="$1"
  if [[ -f "$HOOK_DIR/$delegate" ]]; then
    echo "$HOOK_DIR/$delegate"
  else
    echo "$HOOK_DIR/../../../core/hooks/$delegate"
  fi
}

run_delegate() {
  local delegate="$1" errf rc
  errf=$(mktemp "${TMPDIR:-/tmp}/cursor-stop-err.XXXXXX")

  set +e
  bash "$(delegate_path "$delegate")" <<<"$INPUT" >/dev/null 2>"$errf"
  rc=$?
  set -e

  if [[ "$rc" -eq 0 ]]; then
    if [[ -s "$errf" ]]; then
      cat "$errf" >&2
    fi
    rm -f "$errf"
    return 0
  fi
  if [[ -s "$errf" ]]; then
    cat "$errf" >&2
  fi
  if [[ "$rc" -eq 2 ]]; then
    cos_log_hook cursor-stop-dispatch block "delegate=${delegate}"
    rm -f "$errf"
    exit 2
  fi

  cos_log_hook cursor-stop-dispatch warn "delegate=${delegate} rc=${rc}"
  rm -f "$errf"
  return 0
}

for delegate in session-end.sh check-capture-worked.sh; do
  run_delegate "$delegate"
done

printf '{}\n'

exit 0
