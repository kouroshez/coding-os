#!/usr/bin/env bash
# reclaim-sweep.sh (Phase G) — SessionStart hook.
#
# Event-independent zombie recovery (TASK-210 RC4). Every new session
# reclaims the zombie in_progress/testing tasks left by DEAD predecessor
# sessions before doing any work. This is the consumer-robust recovery
# leg: it does NOT rely on the dying session running anything (the Claude
# runtime fires zero SessionEnd hooks, so a kill/crash/context-exhaustion
# runs no closure path) nor on the nightly cron (macOS-launchd, opt-in).
# The NEXT session that connects cleans up its predecessor.
#
# Reclaim itself is conservative — it only touches a task whose owner
# session is inactive AND which has been idle past its per-status window
# (board_os.cos_task_reclaim), so a concurrently-active peer's card is
# never yanked. Fire-and-forget, detached, never blocks session start.
# Debounced ~30 min via $COS_PANEL_DIR/.reclaim-sweep so rapid resumes in
# one work burst don't re-run it.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook reclaim-sweep enter || true

# Only when a board DB and the cos CLI both exist (the CLI runs on-disk
# code, so it always reflects the current reclaim logic).
[ -f "${COS_DB_PATH:-}" ] || exit 0
command -v cos >/dev/null 2>&1 || exit 0

# Upgrade panel id from the SessionStart payload so the debounce marker
# lands in THIS panel (TASK-035 / TASK-107).
INPUT="$(cos_read_stdin_bounded 2 2>/dev/null || true)"
command -v cos_panel_upgrade_from_payload >/dev/null 2>&1 \
  && cos_panel_upgrade_from_payload "$INPUT" 2>/dev/null || true

# Time-debounce: skip if a sweep ran in the last 30 min for this panel.
MARKER="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.reclaim-sweep"
if [ -f "$MARKER" ]; then
  if [ "$(uname)" = "Darwin" ]; then
    LAST=$(stat -f %m "$MARKER" 2>/dev/null || echo 0)
  else
    LAST=$(stat -c %Y "$MARKER" 2>/dev/null || echo 0)
  fi
  NOW=$(date +%s)
  if [ $((NOW - LAST)) -lt 1800 ]; then
    cos_log_hook reclaim-sweep skip "reason=debounced" || true
    exit 0
  fi
fi
: > "$MARKER" 2>/dev/null || true

# Detached + bounded — must never delay session startup. The reclaim is a
# quick read + a few row updates; background it so a slow CLI cold-start
# never blocks the user's first prompt.
( cos task-reclaim >/dev/null 2>&1 || true ) &

cos_log_hook reclaim-sweep ok || true
exit 0
