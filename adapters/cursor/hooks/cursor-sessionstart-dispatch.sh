#!/usr/bin/env bash
# Cursor sessionStart dispatcher: run session hooks; emit Cursor JSON
# (`additional_context` / optional `env`) instead of Codex SessionStart schema.
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$HOOK_DIR/cos-env.sh" 2>/dev/null || source "$HOOK_DIR/../../../core/hooks/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then
  cos_log_hook() { :; }
fi

INPUT=$(cat)
COS_HOOK_RUNTIME_MODEL="$(printf '%s' "$INPUT" | jq -r '.model // empty' 2>/dev/null || true)"
export COS_HOOK_RUNTIME_MODEL
# Cursor sessionStart JSON has no `source`; synthesize for core hooks.
SYNTH=$(printf '%s' "$INPUT" | jq -c '
  if (has("source")|not) or (.source == null) or (.source == "")
  then . + {source:"startup"} else . end
' 2>/dev/null || echo '{"source":"startup"}')

SOURCE=$(printf '%s' "$SYNTH" | jq -r '.source // "startup"' 2>/dev/null || echo "startup")
cos_log_hook cursor-sessionstart-dispatch fire "source=${SOURCE}"

delegate_path() {
  local delegate="$1"
  if [[ -f "$HOOK_DIR/$delegate" ]]; then
    echo "$HOOK_DIR/$delegate"
  else
    echo "$HOOK_DIR/../../../core/hooks/$delegate"
  fi
}

CAPTURED_FILE="$(mktemp "${TMPDIR:-/tmp}/cursor-sessionstart.XXXXXX")"
trap 'rm -f "$CAPTURED_FILE"' EXIT

for delegate in session-context.sh warn-mcp-down.sh remind-daily.sh; do
  DELEGATE_PATH="$(delegate_path "$delegate")"
  if ! bash "$DELEGATE_PATH" <<< "$SYNTH" >>"$CAPTURED_FILE" 2>&1; then
    cos_log_hook cursor-sessionstart-dispatch warn "delegate=${delegate} source=${SOURCE}"
  fi
done

python3 - "$CAPTURED_FILE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
# Cursor sessionStart output schema (snake_case per Cursor hooks docs).
payload = {"additional_context": text.strip()}
json.dump(payload, sys.stdout, ensure_ascii=False)
sys.stdout.write("\n")
PY

exit 0
