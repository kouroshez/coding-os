#!/usr/bin/env bash
# Codex SessionStart dispatcher: sequence context recovery and MCP liveness,
# then emit the response in Codex's required JSON schema.
#
# Per developers.openai.com/codex/hooks (Apr 2026), a SessionStart hook MUST
# write a JSON object to stdout. Plain text — what our upstream dispatches
# emit for human readability — fails with "invalid session start JSON output".
# This wrapper:
#   1. Captures stdout from session-context.sh + warn-mcp-down.sh.
#   2. Forwards their stderr unchanged (user-visible warnings still show).
#   3. Emits `{"hookSpecificOutput": {"hookEventName": "SessionStart",
#      "additionalContext": "<captured>"}}` so Codex can inject the
#      captured banner into the agent's prompt.
# Exit 0 always — SessionStart cannot block. Delegate failures become log
# entries and a stderr warning but never fail the session.
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$HOOK_DIR/cos-env.sh" 2>/dev/null || source "$HOOK_DIR/../../../core/hooks/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then
  cos_log_hook() { :; }
fi

INPUT=$(cat)
SOURCE=$(echo "$INPUT" | jq -r '.source // "startup"' 2>/dev/null || echo "startup")
cos_log_hook codex-sessionstart-dispatch fire "source=${SOURCE}"

delegate_path() {
  local delegate="$1"
  if [[ -f "$HOOK_DIR/$delegate" ]]; then
    echo "$HOOK_DIR/$delegate"
  else
    echo "$HOOK_DIR/../../../core/hooks/$delegate"
  fi
}

# Collect delegate stdout into a temp file; stderr flows through so the
# user still sees warnings (e.g. MCP-down banner). We never let a delegate
# fault bubble into the wrapper — SessionStart must exit 0.
CAPTURED_FILE="$(mktemp "${TMPDIR:-/tmp}/codex-sessionstart.XXXXXX")"
trap 'rm -f "$CAPTURED_FILE"' EXIT

for delegate in session-context.sh warn-mcp-down.sh check-mcp-extras.sh remind-daily.sh agent-presence.sh; do
  DELEGATE_PATH="$(delegate_path "$delegate")"
  if ! bash "$DELEGATE_PATH" <<< "$INPUT" >>"$CAPTURED_FILE" 2>&1 ; then
    cos_log_hook codex-sessionstart-dispatch warn "delegate=${delegate} source=${SOURCE}"
  fi
done

# Wrap captured text in the JSON schema Codex expects. Python is the only
# dependency we can rely on for safe JSON encoding (jq is not always
# installed) and it handles UTF-8 + embedded quotes/newlines natively.
HELPER="$(dirname "$0")/../../../core/hooks/_helpers/wrap_dispatch_output.py"
if [[ -f "$HELPER" ]]; then
  python3 "$HELPER" additional-context SessionStart "$CAPTURED_FILE"
fi

exit 0
