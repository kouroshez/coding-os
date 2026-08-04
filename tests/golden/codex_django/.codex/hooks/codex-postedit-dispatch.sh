#!/usr/bin/env bash
set -euo pipefail

export COS_AGENT=codex
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$HOOK_DIR/cos-env.sh" 2>/dev/null || source "$HOOK_DIR/../../../core/hooks/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cat 2>/dev/null || true)"
if command -v cos_panel_upgrade_from_payload >/dev/null 2>&1; then
  cos_panel_upgrade_from_payload "$INPUT" >/dev/null 2>&1 || true
fi

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/codex-postedit.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT
NORMALIZED="$WORK_DIR/normalized.jsonl"
if ! printf '%s' "$INPUT" | python3 "$HOOK_DIR/codex-normalize-edit.py" >"$NORMALIZED" 2>"$WORK_DIR/normalize.err"; then
  cat "$WORK_DIR/normalize.err" >&2
  cos_log_hook codex-postedit-dispatch warn "reason=unparseable-patch"
  printf '{}\n'
  exit 0
fi

delegate_path() {
  local delegate="$1"
  if [[ -f "$HOOK_DIR/$delegate" ]]; then
    printf '%s\n' "$HOOK_DIR/$delegate"
  else
    printf '%s\n' "$HOOK_DIR/../../../core/hooks/$delegate"
  fi
}

OUTPUTS=()
RUN_INDEX=0
run_delegate() {
  local payload="$1" delegate="$2" output error rc
  RUN_INDEX=$((RUN_INDEX + 1))
  output="$WORK_DIR/$RUN_INDEX.out"
  error="$WORK_DIR/$RUN_INDEX.err"
  set +e
  bash "$(delegate_path "$delegate")" <<<"$payload" >"$output" 2>"$error"
  rc=$?
  set -e
  [[ -s "$output" ]] && OUTPUTS+=("$output")
  [[ -s "$error" ]] && cat "$error" >&2
  if [[ "$rc" -ne 0 ]]; then
    cos_log_hook codex-postedit-dispatch warn "delegate=$delegate rc=$rc"
  fi
}

while IFS= read -r payload; do
  for delegate in \
    lint-task.sh \
    enforce-doc-sync.sh \
    verify-rename-callers.sh \
    advance-role.sh \
    track-discovery.sh \
    auto-reindex-docs.sh \
    auto-regen-doc-index.sh \
    auto-task-sync.sh \
    capture-observation.sh \
    capture-work-log.sh \
    agent-presence.sh \
    nudge-reuse-first.sh \
    check-doc-size.sh \
    regen-reminder.sh \
    test-first-reminder.sh \
    check-agents-md-size.sh \
    check-agents-md-refs.sh \
    remind-dogfood.sh; do
    run_delegate "$payload" "$delegate"
  done
done <"$NORMALIZED"

python3 "$HOOK_DIR/codex-merge-hook-output.py" PostToolUse "${OUTPUTS[@]}"
