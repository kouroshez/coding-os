#!/usr/bin/env bash
# Cursor preToolUse Write matcher: run Write|Edit enforcement chain (registry order).
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$HOOK_DIR/cos-env.sh" 2>/dev/null || source "$HOOK_DIR/../../../core/hooks/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then
  cos_log_hook() { :; }
fi

INPUT=$(cat)
COS_HOOK_RUNTIME_MODEL="$(printf '%s' "$INPUT" | jq -r '.model // empty' 2>/dev/null || true)"
export COS_HOOK_RUNTIME_MODEL
cos_log_hook cursor-pretool-write-dispatch fire "tool=Write"

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
  errf=$(mktemp "${TMPDIR:-/tmp}/cursor-pwrite-err.XXXXXX")
  set +e
  bash "$(delegate_path "$delegate")" <<<"$INPUT" >/dev/null 2>"$errf"
  rc=$?
  set -e

  if [[ "$rc" -eq 0 ]]; then
    rm -f "$errf"
    return 0
  fi
  if [[ "$rc" -eq 2 ]]; then
    cos_log_hook cursor-pretool-write-dispatch block "delegate=${delegate}"
    cat "$errf" >&2
    rm -f "$errf"
    exit 2
  fi
  cos_log_hook cursor-pretool-write-dispatch warn "delegate=${delegate} rc=${rc}"
  if [[ -s "$errf" ]]; then
    cat "$errf" >&2
  fi
  rm -f "$errf"
  return 0
}

for delegate in \
  block-secrets.sh \
  block-bad-patterns.sh \
  block-protected-files.sh \
  block-migration-conflict.sh \
  block-hardcoded-literals.sh \
  enforce-template.sh \
  thinking-os-gate.sh \
  enforce-task-start.sh \
  enforce-doc-anchor.sh \
  enforce-memory-check.sh \
  enforce-skill.sh \
  enforce-zoom.sh \
  enforce-graph-context.sh \
  enforce-rename-plan.sh \
  validate-task-frontmatter.sh \
  enforce-wip-limit.sh \
  warn-template-drift.sh \
  enforce-anti-ambiguity.sh; do
  run_delegate "$delegate"
done

exit 0
