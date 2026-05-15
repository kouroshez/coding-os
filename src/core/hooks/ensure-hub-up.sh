#!/usr/bin/env bash
# SessionStart hook: ensure the global coding-os Hub daemon is up.
#
# Rationale: the Hub (cos hub on port 9188) is the single web entry point
# that lists every registered project and serves board/graph/search/
# cognition for each one.  Without it, a user who opens localhost:9188
# in the browser sees a connection refused — but we do not want to force
# autostart on privacy/battery-conscious users.
#
# Policy:
#   - Runs only if .coding-os.yaml has `hub.enabled: true` (default true).
#   - If already reachable → silent exit.
#   - If down → start it in the background (`cos hub start`).  Never blocks.
#   - Never forces the human to keep the daemon running; `cos hub stop` +
#     `hub.enabled: false` opts out.
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$HOOK_DIR/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then
  cos_log_hook() { :; }
fi

PROJECT_ROOT="$(cd "$HOOK_DIR/../.." && pwd)"
CONFIG="$PROJECT_ROOT/.coding-os.yaml"
HUB_PORT="${COS_HUB_PORT:-9188}"

cos_log_hook ensure-hub-up fire

# ── Policy check: hub.enabled must be true (default true if not set).
if [[ -f "$CONFIG" ]]; then
  DISABLED=$(python3 -c '
import sys
try:
    import yaml
except Exception:
    sys.exit(0)
try:
    data = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
except Exception:
    sys.exit(0)
hub = (data.get("hub") or {})
# Treat missing key as enabled=true.
print("1" if hub.get("enabled", True) is False else "0")
' "$CONFIG" 2>/dev/null || echo "0")
  if [[ "$DISABLED" == "1" ]]; then
    cos_log_hook ensure-hub-up skip "reason=hub_disabled"
    exit 0
  fi
fi

# ── Probe: is something already answering on 127.0.0.1:$HUB_PORT ?
if curl -fsS --max-time 0.5 "http://127.0.0.1:${HUB_PORT}/health" >/dev/null 2>&1; then
  cos_log_hook ensure-hub-up ok "reason=already_up"
  exit 0
fi

# ── Start detached.  `cos hub start` itself spawns with start_new_session.
if command -v cos >/dev/null 2>&1; then
  (cos hub start --port "$HUB_PORT" >/dev/null 2>&1 &) || true
  cos_log_hook ensure-hub-up warn "action=started_background port=${HUB_PORT}"
  echo "[coding-os] Hub starting on http://127.0.0.1:${HUB_PORT} (background)"
else
  cos_log_hook ensure-hub-up skip "reason=cos_not_on_path"
fi

exit 0
