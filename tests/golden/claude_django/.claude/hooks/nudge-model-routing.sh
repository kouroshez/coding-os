#!/usr/bin/env bash
# UserPromptSubmit hook — supervision directive injector.
#
# When hub-settings.json::model_routing.enabled is true, inject a ONE-LINE
# directive (once per session) telling the agent how the selected trigger
# mode controls formula dispatch. Toggle off = exit silently before any output: zero
# injected tokens, zero behavior change. Fail-open: never blocks a prompt.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

SETTINGS_FILE="${COS_STATE_DIR:-.coding-os}/hub-settings.json"
[[ -f "$SETTINGS_FILE" ]] || exit 0

ENABLED=$(jq -r '.model_routing.enabled // false' "$SETTINGS_FILE" 2>/dev/null || echo "false")
[[ "$ENABLED" == "true" ]] || exit 0

# Once per session — same marker family as the other nudges; the panel dir
# is cleared at SessionStart so a new session re-injects exactly once.
MARKER="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.model-routing-nudged"
[[ -f "$MARKER" ]] && exit 0
touch "$MARKER" 2>/dev/null || true

MODE=$(jq -r '.model_routing.mode // "explicit"' "$SETTINGS_FILE" 2>/dev/null || echo "explicit")
THRESHOLD=$(jq -r '.model_routing.complexity_threshold // "COMPLICATED"' "$SETTINGS_FILE" 2>/dev/null || echo "COMPLICATED")
CONTEXT="[agent-supervision ON] mode=${MODE}, threshold=${THRESHOLD}. Follow src/core/rules/model-routing.md: role policies choose adapter/model/effort; dispatch tools enforce capacity cooldown, safe fallback, and recovery."

cos_log_hook nudge-model-routing ok || true
printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":$(printf '%s' "$CONTEXT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}"

exit 0
