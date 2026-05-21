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

HELPER="$(dirname "$0")/../../../core/hooks/_helpers/wrap_dispatch_output.py"
if [[ -f "$HELPER" ]]; then
  # Cursor sessionStart schema (snake_case per Cursor hooks docs).
  python3 "$HELPER" additional-context-flat "$CAPTURED_FILE"
fi

exit 0
