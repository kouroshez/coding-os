#!/usr/bin/env bash
set -euo pipefail

export COS_AGENT=codex
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$HOOK_DIR/cos-env.sh" 2>/dev/null || source "$HOOK_DIR/../../../core/hooks/cos-env.sh" 2>/dev/null || true

INPUT="$(cos_read_stdin_bounded 2)"
if command -v cos_panel_upgrade_from_payload >/dev/null 2>&1; then
  cos_panel_upgrade_from_payload "$INPUT" >/dev/null 2>&1 || true
fi

for delegate in agent-presence.sh; do
  if [[ -f "$HOOK_DIR/$delegate" ]]; then
    DELEGATE_PATH="$HOOK_DIR/$delegate"
  else
    DELEGATE_PATH="$HOOK_DIR/../../../core/hooks/$delegate"
  fi
  bash "$DELEGATE_PATH" <<<"$INPUT"
done
