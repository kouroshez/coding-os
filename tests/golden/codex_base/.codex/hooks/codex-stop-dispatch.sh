#!/usr/bin/env bash
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$HOOK_DIR/cos-env.sh" 2>/dev/null || source "$HOOK_DIR/../../../core/hooks/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then
  cos_log_hook() { :; }
fi

INPUT=$(cat)
if command -v cos_panel_upgrade_from_payload >/dev/null 2>&1; then
  cos_panel_upgrade_from_payload "$INPUT" >/dev/null 2>&1 || true
fi
cos_log_hook codex-stop-dispatch fire

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/codex-stop.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT
OUTPUTS=()
RUN_INDEX=0

delegate_path() {
  local delegate="$1"
  if [[ -f "$HOOK_DIR/$delegate" ]]; then
    printf '%s\n' "$HOOK_DIR/$delegate"
  else
    printf '%s\n' "$HOOK_DIR/../../../core/hooks/$delegate"
  fi
}

run_delegate() {
  local delegate="$1"
  local stdout_file stderr_file rc
  RUN_INDEX=$((RUN_INDEX + 1))
  stdout_file="$WORK_DIR/$RUN_INDEX.out"
  stderr_file="$WORK_DIR/$RUN_INDEX.err"

  set +e
  bash "$(delegate_path "$delegate")" <<< "$INPUT" >"$stdout_file" 2>"$stderr_file"
  rc=$?
  set -e

  [[ -s "$stdout_file" ]] && OUTPUTS+=("$stdout_file")
  if [[ -s "$stderr_file" ]]; then
    cat "$stderr_file" >&2
  fi
  if [[ "$rc" -eq 0 ]]; then
    return 0
  fi
  if [[ "$rc" -eq 2 ]]; then
    cos_log_hook codex-stop-dispatch block "delegate=${delegate}"
    exit 2
  fi

  cos_log_hook codex-stop-dispatch warn "delegate=${delegate} rc=${rc}"
  return 0
}

for delegate in session-end.sh warn-abandoned-task.sh nudge-learn-narrative.sh check-capture-worked.sh auto-trace-rotate.sh snapshot-transcript.sh drain-embedding-outbox.sh agent-presence.sh; do
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
python3 "$MERGER" Stop "${OUTPUTS[@]}"
