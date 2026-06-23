#!/usr/bin/env bash
# Codex SessionStart dispatcher: sequence context recovery and MCP liveness,
# then emit the response in Codex's required JSON schema.
#
# Per developers.openai.com/codex/hooks (Apr 2026), a SessionStart hook MUST
# write a JSON object to stdout. Plain text — what our upstream dispatches
# emit for human readability — fails with "invalid session start JSON output".
# This wrapper:
#   1. Runs each delegate (the full Bash-runnable SessionStart set — context,
#      MCP/extras health, the prime cards, decay, presence), capturing each
#      delegate's stdout+stderr and unwrapping any Claude-style
#      {"hookSpecificOutput":{additionalContext}} envelope via
#      extract_additional_context.py so prime cards render as text.
#   2. Concatenates the unwrapped output (delegate warnings included) into one
#      card.
#   3. Emits `{"hookSpecificOutput": {"hookEventName": "SessionStart",
#      "additionalContext": "<card>"}}` so Codex injects it into the prompt.
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

# Collect delegate output into a temp file. Many delegates are the SAME
# scripts Claude runs and emit a Claude-style JSON envelope
# ({"hookSpecificOutput":{"additionalContext": "<card>"}}) on stdout —
# concatenating that raw would surface literal JSON to the agent, so each
# delegate's output is piped through extract_additional_context.py which
# unwraps the envelope (and passes plain-text / stderr warnings through
# unchanged). We never let a delegate fault bubble into the wrapper —
# SessionStart must exit 0.
CAPTURED_FILE="$(mktemp "${TMPDIR:-/tmp}/codex-sessionstart.XXXXXX")"
trap 'rm -f "$CAPTURED_FILE"' EXIT

EXTRACT="$HOOK_DIR/../../../core/hooks/_helpers/extract_additional_context.py"

# Delegate order: workflow banner → MCP/extras health → prime cards
# (intent / rules / required-skill / audit-resume) → daily + graph nudges →
# memory decay → presence. Prime cards mirror Claude's SessionStart set so a
# resumed Codex session re-enters with the same workflow-integrity context.
for delegate in \
  session-context.sh \
  warn-mcp-down.sh \
  check-mcp-extras.sh \
  intent-primer.sh \
  rules-primer.sh \
  session-skill-primer.sh \
  inject-resume-prompt.sh \
  remind-daily.sh \
  warn-graph-empty.sh \
  auto-brain-decay.sh \
  agent-presence.sh \
  pr-reap.sh; do
  DELEGATE_PATH="$(delegate_path "$delegate")"
  if DELEGATE_OUT="$(bash "$DELEGATE_PATH" <<< "$INPUT" 2>&1)"; then :; else
    cos_log_hook codex-sessionstart-dispatch warn "delegate=${delegate} source=${SOURCE}"
  fi
  if [[ -n "${DELEGATE_OUT:-}" ]]; then
    if [[ -f "$EXTRACT" ]]; then
      printf '%s' "$DELEGATE_OUT" | python3 "$EXTRACT" >>"$CAPTURED_FILE" 2>/dev/null \
        || printf '%s' "$DELEGATE_OUT" >>"$CAPTURED_FILE"
    else
      printf '%s' "$DELEGATE_OUT" >>"$CAPTURED_FILE"
    fi
    printf '\n' >>"$CAPTURED_FILE"
  fi
  DELEGATE_OUT=""
done

# Wrap captured text in the JSON schema Codex expects. Python is the only
# dependency we can rely on for safe JSON encoding (jq is not always
# installed) and it handles UTF-8 + embedded quotes/newlines natively.
HELPER="$(dirname "$0")/../../../core/hooks/_helpers/wrap_dispatch_output.py"
if [[ -f "$HELPER" ]]; then
  python3 "$HELPER" additional-context SessionStart "$CAPTURED_FILE"
fi

exit 0
