#!/usr/bin/env bash
# Codex PostToolUse (Bash) dispatcher — runs remind-learn-validate then
# agent-presence so the live panel sees tool completions (not only
# PreToolUse / prompts).  Mirrors codex-userpromptsubmit-dispatch.sh.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/cos-env.sh" 2>/dev/null || true

INPUT="$(cat 2>/dev/null || true)"

delegate_path() {
  local name="$1"
  if [[ -f "${SCRIPT_DIR}/${name}" ]]; then
    echo "${SCRIPT_DIR}/${name}"
  else
    echo "${SCRIPT_DIR}/../../../core/hooks/${name}"
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
    cos_log_hook codex-posttool-dispatch warn "delegate=${name} failed" 2>/dev/null || true
  fi
  return 0
}

# Order + set MUST match adapter.yaml::hook_dispatchers[PostToolUse].delegates
# (asserted by tests/test_adapter_parity.py). auto-reindex-shell-ops
# + auto-prune-deleted-files keep the codex graph fresh after shell mv/rm.
for delegate in \
  remind-learn-validate.sh \
  auto-reindex-shell-ops.sh \
  auto-prune-deleted-files.sh \
  search-verify-remaining.sh \
  advance-role.sh \
  sync-task-current.sh \
  agent-presence.sh; do
  run_delegate "$delegate"
done

exit 0
