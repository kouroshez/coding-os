#!/usr/bin/env bash
# inject-mcp-caller-session.sh — attribute MCP task writes to the
# REAL calling panel under concurrent same-agent panels.
#
# PreToolUse hook on the attribution-critical MCP task tools. The long-lived MCP
# server is panel-blind (ONE process for ALL panels of an agent) and otherwise
# guesses the caller via the last-writer-wins .active-session pointer — so a task
# moved by panel A can be stamped with panel B's session, breaking per-session
# WIP, zombie reclaim, and banner/DB agreement. This hook reads THIS panel's
# coding-os session from $COS_SESSION_FILE and injects it as `agent_session`
# (resolve_agent_session treats an explicit arg as the highest-priority signal)
# via hookSpecificOutput.updatedInput. Completes F2.
#
# FAIL-OPEN ALWAYS: a missing dep / unresolved session / parse error emits
# nothing and exits 0, so the tool runs with its ORIGINAL args (status quo).
# This hook can never block or corrupt an MCP call. Hence `set -uo pipefail`
# WITHOUT -e: a single failed command must not abort before the final exit 0.
set -uo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2 2>/dev/null || true)"
[[ -z "$INPUT" ]] && exit 0

# Resolve THIS panel from the stdin payload (strongest signal) before reading
# the per-panel session file, so two sibling tabs never cross.
cos_panel_upgrade_from_payload "$INPUT" >/dev/null 2>&1 || true

# jq is required to rewrite the JSON args safely. We must NOT block the MCP
# call (fail-open on the call), but the degradation must NOT be SILENT: without
# injection, per-panel attribution is lost and the per-session WIP cap can
# collapse across sibling panels. Warn once per session (debounced by a
# persistent diagnostic marker) + log telemetry, then let the call proceed.
if ! command -v jq >/dev/null 2>&1; then
  _deg_marker="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.mcp-attribution-degraded"
  if [[ ! -f "$_deg_marker" ]]; then
    echo "warning: jq not found — MCP caller-session attribution is DISABLED; per-session WIP cap may collapse across sibling panels. Install jq to restore per-panel isolation." >&2
    printf 'jq-missing\n' > "$_deg_marker" 2>/dev/null || true
  fi
  cos_log_hook inject-mcp-caller-session warn "reason=jq-missing" || true
  exit 0
fi

SID="$(cos_current_session 2>/dev/null || true)"
# Inject only a GENUINE coding-os session id (ses-<agent>-…). cos_current_session
# falls back to the panel-id / ppid-hash when no session-id file exists yet;
# injecting that as agent_session would corrupt attribution worse than the
# status quo, so do not inject on anything that is not a real session token.
# This is benign-normal early in a session (before the session-id file exists),
# so it stays quiet on stderr but is logged for observability (not silent).
if [[ "$SID" != ses-* ]]; then
  cos_log_hook inject-mcp-caller-session skip "reason=no-session-id" || true
  exit 0
fi

# Inject only when the caller passed NO explicit agent_session; emit updatedInput
# only when we actually add it (jq `empty` → no stdout → no-override path).
OUT="$(printf '%s' "$INPUT" | jq -c --arg sid "$SID" '
  (.tool_input // {}) as $ti
  | if (($ti.agent_session // "") | tostring | length) > 0 then empty
    else {hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "allow", updatedInput: ($ti + {agent_session: $sid})}}
    end
' 2>/dev/null || true)"

if [[ -n "$OUT" ]]; then
  printf '%s\n' "$OUT"
  cos_log_hook inject-mcp-caller-session ok "sid=${SID##*-}" || true
fi
exit 0
