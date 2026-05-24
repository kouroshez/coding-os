#!/usr/bin/env bash
# Codex PreToolUse dispatcher: run Bash guardrails sequentially.
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$HOOK_DIR/cos-env.sh" 2>/dev/null || source "$HOOK_DIR/../../../core/hooks/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then
  cos_log_hook() { :; }
fi

INPUT=$(cat)
cos_log_hook codex-pretool-dispatch fire "tool=Bash"

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
  stdout_file=$(mktemp "${TMPDIR:-/tmp}/codex-pretool-out.XXXXXX")
  stderr_file=$(mktemp "${TMPDIR:-/tmp}/codex-pretool-err.XXXXXX")

  set +e
  bash "$(delegate_path "$delegate")" <<< "$INPUT" >"$stdout_file" 2>"$stderr_file"
  rc=$?
  set -e

  if [[ "$rc" -eq 0 ]]; then
    rm -f "$stdout_file" "$stderr_file"
    return 0
  fi
  if [[ "$rc" -eq 2 ]]; then
    cos_log_hook codex-pretool-dispatch block "delegate=${delegate}"
    cat "$stderr_file" >&2
    rm -f "$stdout_file" "$stderr_file"
    exit 2
  fi

  cos_log_hook codex-pretool-dispatch warn "delegate=${delegate} rc=${rc}"
  if [[ -s "$stderr_file" ]]; then
    cat "$stderr_file" >&2
  fi
  rm -f "$stdout_file" "$stderr_file"
  return 0
}

for delegate in \
  block-secrets.sh \
  block-dangerous-commands.sh \
  branch-guard.sh \
  enforce-commit-message.sh \
  block-uv-heredoc.sh \
  enforce-verify.sh \
  search-enforce-inventory.sh \
  agent-presence.sh; do
  run_delegate "$delegate"
done

exit 0
