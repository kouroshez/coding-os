#!/usr/bin/env bash
# resolve-supervise-route.sh (UserPromptSubmit) — make the routing policy apply.
#
# nudge-model-routing.sh announces that supervision is ON; this hook is what
# makes it MEAN something per prompt: it resolves the active role through the
# dispatcher's own precedence and stamps .supervise-route so the transparency
# banner can name the adapter/model and the agent can pass them when it
# dispatches. Read-only — no child process, no provider token, no probe.
#
# Debounce: once per session per (gate-class, role) — a role advance re-resolves,
# an unchanged turn does not. Fail-open: any error exits 0.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

SETTINGS_FILE="${COS_STATE_DIR:-.coding-os}/hub-settings.json"
[[ -f "$SETTINGS_FILE" ]] || exit 0

ENABLED=$(jq -r '.model_routing.enabled // false' "$SETTINGS_FILE" 2>/dev/null || echo "false")
[[ "$ENABLED" == "true" ]] || exit 0

PANEL_DIR="${COS_PANEL_DIR:-${COS_AGENT_DIR:-${COS_STATE_DIR:-.coding-os}/${COS_AGENT:-claude}}}"

GATE_FILE="${PANEL_DIR}/.thinking_os-gate"
GATE_VALUE=""
if [[ -f "$GATE_FILE" ]]; then
  source "$(dirname "$0")/check-state.sh" 2>/dev/null || true
  if type check_state >/dev/null 2>&1; then
    check_state "$GATE_FILE" 7200
    [[ "${STATE_VALID:-}" == "true" ]] && GATE_VALUE="${STATE_VALUE:-}"
  else
    GATE_VALUE=$(head -1 "$GATE_FILE" 2>/dev/null | cut -d' ' -f2- || true)
  fi
fi
GATE_CLASS=$(printf '%s' "$GATE_VALUE" | awk '{print $1}')

# Debounce on (gate-class, active role): advancing the chain must re-resolve,
# because the next role may be pinned to a different adapter.
ACTIVE_ROLE=""
[[ -f "${PANEL_DIR}/.role" ]] && ACTIVE_ROLE=$(tr -d '\n\r' < "${PANEL_DIR}/.role" 2>/dev/null || true)
MARKER="${PANEL_DIR}/.supervise-route-resolved"
SIGNATURE="${GATE_CLASS}:${ACTIVE_ROLE}"
if [[ -f "$MARKER" ]]; then
  LAST=$(head -1 "$MARKER" 2>/dev/null | tr -d '\n\r' || true)
  [[ "$LAST" == "$SIGNATURE" ]] && exit 0
fi

# Resolve the helper through the hook symlink (core dirs reach consumers as
# live symlinks, so $0's dirname is the consumer copy, not the source tree).
_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
  _dir="$(cd -P "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ "$_src" != /* ]] && _src="$_dir/$_src"
done
HSRC="$(cd -P "$(dirname "$_src")" && pwd)"
HELPER="${HSRC}/_helpers/resolve_supervise_route.py"
[[ -f "$HELPER" ]] || exit 0

# Bare python3 cannot import the policy module (pydantic lives in cos's own
# environment). Resolving the interpreter is not an optimisation here — it is the
# difference between this hook working and failing open forever.
COS_PY="$(cos_resolve_python 2>/dev/null || echo python3)"
[[ -x "$COS_PY" ]] || COS_PY=python3

set +e
OUT=$("$COS_PY" "$HELPER" "${GATE_CLASS:-}" "$PANEL_DIR" 2>/dev/null)
HELPER_RC=$?
set -e

# Debounce only a run that actually resolved. Stamping the marker after a broken
# helper is what turns one bad turn into a silent session-long outage.
if [[ "$HELPER_RC" -eq 0 ]]; then
  mkdir -p "$(dirname "$MARKER")" 2>/dev/null || true
  printf '%s' "$SIGNATURE" > "$MARKER" 2>/dev/null || true
else
  cos_log_hook resolve-supervise-route warn \
    "helper rc=${HELPER_RC} py=${COS_PY##*/} — route unresolved" || true
  exit 0
fi

if [[ -n "$OUT" ]]; then
  cos_log_hook resolve-supervise-route ok "gate=${GATE_CLASS:-unset} role=${ACTIVE_ROLE:-none}" || true
  printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":$(printf '%s' "$OUT" | "$COS_PY" -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}"
else
  cos_log_hook resolve-supervise-route ok "gate=${GATE_CLASS:-unset} resolved=none" || true
fi

exit 0
