#!/usr/bin/env bash
# warn-graph-empty.sh (Phase I.10) — SessionStart.
#
# PURPOSE: Surface a one-line warning when graph_os has no data yet so
#   the agent knows `cos_graph_*` queries will return empty. Never
#   blocks; never auto-indexes. The user decides when to run
#   `cos graph-reindex`.
#
# Design:
#   - Non-blocking: always exits 0. Agents continue boot even if the
#     hook body fails.
#   - Cheap: one SQLite SELECT with a 250 ms timeout.
#   - Debounced: only fires once per session (marker file). Repeated
#     session-starts within the same `session-id` stay silent.
#   - Fail-soft: missing DB / missing deps / SQL errors log to
#     $COS_STATE_DIR/.warn-graph-empty.log and exit 0.

set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook warn-graph-empty enter || true

STATE_DIR="${COS_STATE_DIR:-$PWD/.coding-os}"
AGENT_DIR="${COS_AGENT_DIR:-${STATE_DIR}/claude}"
DB_PATH="${COS_DB_PATH:-${STATE_DIR}/coding-os.db}"
LOG_FILE="${STATE_DIR}/.warn-graph-empty.log"
MARKER="${COS_PANEL_DIR:-$AGENT_DIR}/.graph-empty-warning-shown"  # panel-first (TASK-107): matches session-context panel-scope clear

mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
mkdir -p "$(dirname "$MARKER")" 2>/dev/null || true

# Debounce — if we warned this session already, skip.
if [[ -f "$MARKER" ]]; then
  cos_log_hook warn-graph-empty skip-debounced || true
  exit 0
fi

# Fast bail: no DB file → graph definitely empty, but also nothing to
# count. Emit the tip anyway.
if [[ ! -f "$DB_PATH" ]]; then
  echo "[graph_os] Graph not indexed yet. Run \`cos graph-reindex\` to enable cos_graph_* queries." >&2
  touch "$MARKER" 2>/dev/null || true
  cos_log_hook warn-graph-empty warn-no-db || true
  exit 0
fi

# Query graph_nodes count. SQLite open + COUNT on indexed table is
# sub-10ms in practice — no timeout wrapper needed (macOS stock lacks
# `timeout`). Missing table → sqlite3 errors to LOG_FILE, COUNT stays
# empty → we stay silent (fail-soft).
COUNT=$(
  sqlite3 "$DB_PATH" \
    "SELECT COUNT(*) FROM graph_nodes;" 2>>"$LOG_FILE" \
  || echo ""
)

if [[ -z "$COUNT" ]]; then
  cos_log_hook warn-graph-empty skip-probe-failed || true
  exit 0
fi

if (( COUNT == 0 )); then
  echo "[graph_os] Graph not indexed yet (graph_nodes=0). Run \`cos graph-reindex\` to enable cos_graph_* queries." >&2
  touch "$MARKER" 2>/dev/null || true
  cos_log_hook warn-graph-empty warn || true
else
  touch "$MARKER" 2>/dev/null || true
  cos_log_hook warn-graph-empty ok "nodes=${COUNT}" || true
fi

# Bounded log file
if [[ -f "$LOG_FILE" ]]; then
  LINES=$(wc -l < "$LOG_FILE" 2>/dev/null || echo 0)
  if (( LINES > 200 )); then
    tail -n 200 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
  fi
fi

exit 0
