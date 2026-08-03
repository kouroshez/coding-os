#!/usr/bin/env bash
set -euo pipefail

export COS_AGENT=codex
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$HOOK_DIR/cos-env.sh" 2>/dev/null || source "$HOOK_DIR/../../../core/hooks/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then
  cos_log_hook() { :; }
fi

INPUT=$(cat)
SOURCE=$(echo "$INPUT" | jq -r '.source // "startup"' 2>/dev/null || echo "startup")
if command -v cos_panel_upgrade_from_payload >/dev/null 2>&1; then
  cos_panel_upgrade_from_payload "$INPUT" >/dev/null 2>&1 || true
fi
cos_log_hook codex-sessionstart-dispatch fire "source=${SOURCE}"

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/codex-sessionstart.XXXXXX")"
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

for delegate in \
  session-context.sh \
  warn-mcp-down.sh \
  check-mcp-extras.sh \
  rules-primer.sh \
  session-skill-primer.sh \
  remind-daily.sh \
  warn-graph-empty.sh \
  auto-brain-decay.sh \
  agent-presence.sh \
  pr-reap.sh; do
  DELEGATE_PATH="$(delegate_path "$delegate")"
  RUN_INDEX=$((RUN_INDEX + 1))
  OUTPUT="$WORK_DIR/$RUN_INDEX.out"
  ERROR="$WORK_DIR/$RUN_INDEX.err"
  set +e
  bash "$DELEGATE_PATH" <<<"$INPUT" >"$OUTPUT" 2>"$ERROR"
  RC=$?
  set -e
  [[ -s "$OUTPUT" ]] && OUTPUTS+=("$OUTPUT")
  [[ -s "$ERROR" ]] && cat "$ERROR" >&2
  if [[ "$RC" -ne 0 ]]; then
    cos_log_hook codex-sessionstart-dispatch warn "delegate=${delegate} source=${SOURCE}"
  fi
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
python3 "$MERGER" SessionStart "${OUTPUTS[@]}"
