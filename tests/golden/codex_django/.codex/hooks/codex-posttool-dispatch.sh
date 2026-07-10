#!/usr/bin/env bash
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${HOOK_DIR}/cos-env.sh" 2>/dev/null || source "${HOOK_DIR}/../../../core/hooks/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cat 2>/dev/null || true)"
if command -v cos_panel_upgrade_from_payload >/dev/null 2>&1; then
  cos_panel_upgrade_from_payload "$INPUT" >/dev/null 2>&1 || true
fi
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/codex-posttool.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT
OUTPUTS=()
RUN_INDEX=0

delegate_path() {
  local name="$1"
  if [[ -f "${HOOK_DIR}/${name}" ]]; then
    printf '%s\n' "${HOOK_DIR}/${name}"
  else
    printf '%s\n' "${HOOK_DIR}/../../../core/hooks/${name}"
  fi
}

run_delegate() {
  local name="$1"
  local path output error rc
  path="$(delegate_path "$name")"
  if [[ ! -x "$path" ]]; then
    return 0
  fi
  RUN_INDEX=$((RUN_INDEX + 1))
  output="$WORK_DIR/$RUN_INDEX.out"
  error="$WORK_DIR/$RUN_INDEX.err"
  set +e
  bash "$path" <<<"$INPUT" >"$output" 2>"$error"
  rc=$?
  set -e
  [[ -s "$output" ]] && OUTPUTS+=("$output")
  [[ -s "$error" ]] && cat "$error" >&2
  if [[ "$rc" -ne 0 ]]; then
    cos_log_hook codex-posttool-dispatch warn "delegate=${name} rc=${rc}"
  fi
  return 0
}

for delegate in \
  remind-learn-validate.sh \
  record-verify-auto.sh \
  auto-graph-reconcile-shell.sh \
  search-verify-remaining.sh \
  advance-role.sh \
  sync-task-current.sh \
  agent-presence.sh; do
  run_delegate "$delegate"
done

MERGER="$HOOK_DIR/codex-merge-hook-output.py"
if [[ ! -f "$MERGER" ]]; then
  SCRIPT_SOURCE="${BASH_SOURCE[0]}"
  while [[ -L "$SCRIPT_SOURCE" ]]; do
    SOURCE_DIR="$(cd -P "$(dirname "$SCRIPT_SOURCE")" && pwd)"
    SCRIPT_SOURCE="$(readlink "$SCRIPT_SOURCE")"
    [[ "$SCRIPT_SOURCE" != /* ]] && SCRIPT_SOURCE="$SOURCE_DIR/$SCRIPT_SOURCE"
  done
  MERGER="$(cd -P "$(dirname "$SCRIPT_SOURCE")" && pwd)/codex-merge-hook-output.py"
fi
python3 "$MERGER" PostToolUse "${OUTPUTS[@]}"
