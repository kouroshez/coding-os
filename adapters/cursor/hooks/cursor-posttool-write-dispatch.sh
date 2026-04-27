#!/usr/bin/env bash
# Cursor postToolUse Write matcher: observability + reminders after file writes.
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$HOOK_DIR/cos-env.sh" 2>/dev/null || source "$HOOK_DIR/../../../core/hooks/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then
  cos_log_hook() { :; }
fi

INPUT=$(cat)
COS_HOOK_RUNTIME_MODEL="$(printf '%s' "$INPUT" | jq -r '.model // empty' 2>/dev/null || true)"
export COS_HOOK_RUNTIME_MODEL
cos_log_hook cursor-posttool-write-dispatch fire "tool=Write"

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
  errf=$(mktemp "${TMPDIR:-/tmp}/cursor-postw-err.XXXXXX")
  set +e
  bash "$(delegate_path "$delegate")" <<<"$INPUT" >/dev/null 2>"$errf"
  rc=$?
  set -e
  if [[ "$rc" -eq 0 ]]; then
    rm -f "$errf"
    return 0
  fi
  if [[ "$rc" -eq 2 ]]; then
    cos_log_hook cursor-posttool-write-dispatch block "delegate=${delegate}"
    cat "$errf" >&2
    rm -f "$errf"
    exit 2
  fi
  cos_log_hook cursor-posttool-write-dispatch warn "delegate=${delegate} rc=${rc}"
  if [[ -s "$errf" ]]; then
    cat "$errf" >&2
  fi
  rm -f "$errf"
  return 0
}

for delegate in \
  capture-observation.sh \
  auto-reindex-docs.sh \
  capture-work-log.sh \
  auto-task-sync.sh \
  lint-task.sh \
  verify-changed-file.sh \
  regen-reminder.sh \
  test-first-reminder.sh \
  doc-sync-reminder.sh \
  check-agents-md-size.sh \
  check-agents-md-refs.sh \
  remind-dogfood.sh \
  track-discovery.sh \
  enforce-doc-sync.sh; do
  run_delegate "$delegate"
done

exit 0
