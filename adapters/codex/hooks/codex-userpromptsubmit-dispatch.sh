#!/usr/bin/env bash
# Codex UserPromptSubmit dispatcher — coalesces delegates so sequencing
# is deterministic (Codex fires matching hooks concurrently otherwise).
#
# Delegates (order matters):
#   1. session-context.sh  — same workflow banner Claude shows on prompts.
#   2. agent-presence.sh   — mark the session "active" for the live panel.
#
# Fail-open: any delegate failure is logged but does not block the prompt.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/cos-env.sh" 2>/dev/null || true

INPUT="$(cat 2>/dev/null || true)"

delegate_path() {
  local name="$1"
  if [[ -x "${SCRIPT_DIR}/${name}" ]]; then
    echo "${SCRIPT_DIR}/${name}"
  else
    # Fall back to the core hook — always available via symlink/install.
    echo "${SCRIPT_DIR}/${name}"
  fi
}

run_delegate() {
  local name="$1"
  local path
  path="$(delegate_path "$name")"
  if [[ ! -x "$path" ]]; then
    return 0
  fi
  if ! printf '%s' "$INPUT" | bash "$path" >/dev/null 2>&1; then
    cos_log_hook codex-userpromptsubmit-dispatch warn "delegate=${name} failed"
  fi
  return 0
}

for delegate in session-context.sh agent-presence.sh; do
  run_delegate "$delegate"
done

exit 0
