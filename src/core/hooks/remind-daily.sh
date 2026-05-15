#!/usr/bin/env bash
# Phase L.4 — SessionStart: nag if `cos daily` hasn't run in > 24h.
# Non-blocking warning only; respects solo-dev ADHD concerns (R-L-30
# "Daily streak is observability NOT shame").

set -eu
source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi


cos_log_hook "remind-daily" "entry" 2>/dev/null || true

marker="${COS_AGENT_DIR:-.coding-os/claude}/.daily-last-run"
if [[ -f "$marker" ]]; then
    last_run=$(stat -f %m "$marker" 2>/dev/null || stat -c %Y "$marker" 2>/dev/null || echo 0)
    now=$(date +%s)
    age=$((now - last_run))
    if (( age < 86400 )); then
        exit 0
    fi
    hours=$((age / 3600))
    echo "💡 Daily check-in last ran ${hours}h ago. Run: cos daily"
else
    echo "💡 First session today? Run: cos daily  (see today's board state)"
fi

exit 0
