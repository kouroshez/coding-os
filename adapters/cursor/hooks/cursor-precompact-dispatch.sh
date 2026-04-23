#!/usr/bin/env bash
# Cursor preCompact: re-run session recovery hooks with source=compact; emit JSON.
# https://cursor.com/docs/agent/hooks — preCompact output is { "user_message": "..." }.
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$HOOK_DIR/cos-env.sh" 2>/dev/null || source "$HOOK_DIR/../../../core/hooks/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then
  cos_log_hook() { :; }
fi

INPUT=$(cat)
COS_HOOK_RUNTIME_MODEL="$(printf '%s' "$INPUT" | jq -r '.model // empty' 2>/dev/null || true)"
export COS_HOOK_RUNTIME_MODEL
SYNTH=$(printf '%s' "$INPUT" | jq -c '. + {source:"compact"}' 2>/dev/null || echo '{"source":"compact"}')
cos_log_hook cursor-precompact-dispatch fire

delegate_path() {
  local delegate="$1"
  if [[ -f "$HOOK_DIR/$delegate" ]]; then
    echo "$HOOK_DIR/$delegate"
  else
    echo "$HOOK_DIR/../../../core/hooks/$delegate"
  fi
}

CAPTURED_FILE="$(mktemp "${TMPDIR:-/tmp}/cursor-precompact.XXXXXX")"
trap 'rm -f "$CAPTURED_FILE"' EXIT

for delegate in session-context.sh warn-mcp-down.sh remind-daily.sh; do
  if ! bash "$(delegate_path "$delegate")" <<<"$SYNTH" >>"$CAPTURED_FILE" 2>&1; then
    cos_log_hook cursor-precompact-dispatch warn "delegate=${delegate}"
  fi
done

python3 - "$CAPTURED_FILE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
text = text.strip()
# Cap: preCompact user_message is a user-visible banner, not a full system prompt.
if len(text) > 2400:
    text = text[:2397] + "..."
out: dict[str, str | dict] = {}
if text:
    out["user_message"] = text
json.dump(out, sys.stdout, ensure_ascii=False)
sys.stdout.write("\n")
PY

exit 0
