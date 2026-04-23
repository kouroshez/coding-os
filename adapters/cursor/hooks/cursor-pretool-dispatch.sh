#!/usr/bin/env bash
# Cursor preToolUse dispatcher: run Shell guardrails sequentially (same
# contract as Codex Bash dispatcher; stdin is Cursor tool JSON).
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$HOOK_DIR/cos-env.sh" 2>/dev/null || source "$HOOK_DIR/../../../core/hooks/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then
  cos_log_hook() { :; }
fi

INPUT=$(cat)
COS_HOOK_RUNTIME_MODEL="$(printf '%s' "$INPUT" | jq -r '.model // empty' 2>/dev/null || true)"
export COS_HOOK_RUNTIME_MODEL
cos_log_hook cursor-pretool-dispatch fire "tool=Shell"

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
  errf=$(mktemp "${TMPDIR:-/tmp}/cursor-pretool-err.XXXXXX")

  set +e
  bash "$(delegate_path "$delegate")" <<<"$INPUT" >/dev/null 2>"$errf"
  rc=$?
  set -e

  if [[ "$rc" -eq 0 ]]; then
    rm -f "$errf"
    return 0
  fi
  if [[ "$rc" -eq 2 ]]; then
    cos_log_hook cursor-pretool-dispatch block "delegate=${delegate}"
    cat "$errf" >&2
    rm -f "$errf"
    exit 2
  fi

  cos_log_hook cursor-pretool-dispatch warn "delegate=${delegate} rc=${rc}"
  if [[ -s "$errf" ]]; then
    cat "$errf" >&2
  fi
  rm -f "$errf"
  return 0
}

for delegate in \
  block-secrets.sh \
  block-dangerous-commands.sh \
  block-uv-heredoc.sh \
  enforce-verify.sh; do
  run_delegate "$delegate"
done

exit 0
