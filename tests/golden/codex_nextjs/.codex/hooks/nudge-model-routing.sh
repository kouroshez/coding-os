#!/usr/bin/env bash
# UserPromptSubmit hook — model-routing directive injector (TASK-319).
#
# When hub-settings.json::model_routing.enabled is true, inject a ONE-LINE
# directive (once per session) telling the agent to consult cos_route_model
# at Classify and honor it at dispatch — CLI/VSCode parity with the hub
# chat Auto option. Toggle off = exit silently before any output: zero
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

ORCH=$(jq -r '.model_routing.orchestrator_model // ""' "$SETTINGS_FILE" 2>/dev/null || echo "")
CONTEXT="[model-routing ON] After recording the gate (cos_classify_prompt), call cos_route_model(complexity=<gate>) and honor it at dispatch (pass model+complexity to cos_dispatch_formula_run). Cold history -> orchestrator_model '${ORCH}' (settings), else adapter default. Contract: src/core/rules/model-routing.md"

cos_log_hook nudge-model-routing ok || true
printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":$(printf '%s' "$CONTEXT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}"

exit 0
