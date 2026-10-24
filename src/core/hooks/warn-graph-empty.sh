#!/usr/bin/env bash
# warn-graph-empty.sh — SessionStart.
#
# PURPOSE: Surface a one-line warning when graph_os has no data yet so
#   the agent knows `cos_graph_*` queries will return empty, and otherwise
#   catch the graph up with files changed outside the agent (git pull,
#   branch switch, another editor) since the last session. Never runs a
#   first full index — the user decides when to run `cos graph-reindex`.
#   Catch-up contract: docs/engineering/graph_os-queries.md
#   § Session-start catch-up.
#
# Design:
#   - Non-blocking: always exits 0. Agents continue boot even if the
#     hook body fails.
#   - Cheap: one SQLite SELECT, plus one git rev-parse/diff/ls-files when
#     the graph has nodes; the reindex itself runs detached.
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
MARKER="${COS_PANEL_DIR:-$AGENT_DIR}/.graph-empty-warning-shown"  # panel-first: matches session-context panel-scope clear

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

# Paths changed since the commit the graph last caught up to — committed
# (pull, checkout) plus modified, deleted and untracked — go to one detached
# worker. No marker yet: record HEAD and catch up the working tree only.
graph_catchup() {
  local project head last helpers
  project="$(dirname "$STATE_DIR")"
  head="$(git -C "$project" rev-parse HEAD 2>/dev/null)" || return 0
  local head_marker="${STATE_DIR}/.graph-indexed-head"
  last="$(cat "$head_marker" 2>/dev/null || true)"

  local -a changed=()
  local rel
  # --relative and ls-files both stay inside the project when it is a
  # subdirectory of a larger repository.
  while IFS= read -r -d '' rel; do
    changed+=("${project}/${rel}")
  done < <(
    if [[ -n "$last" && "$last" != "$head" ]] && git -C "$project" cat-file -e "${last}^{commit}" 2>/dev/null; then
      git -C "$project" diff --name-only --relative --no-renames -z "$last" "$head" 2>/dev/null
    fi
    git -C "$project" diff --name-only --relative --no-renames -z HEAD 2>/dev/null
    git -C "$project" ls-files --others --exclude-standard -z 2>/dev/null
  )

  if [[ -z "$last" && ${#changed[@]} -eq 0 ]]; then
    printf '%s\n' "$head" > "$head_marker" 2>/dev/null || true
    return 0
  fi
  if [[ "$last" == "$head" && ${#changed[@]} -eq 0 ]]; then
    cos_log_hook warn-graph-empty catchup-none || true
    return 0
  fi

  helpers="$(dirname "$(_cos_helpers_dir 2>/dev/null)")"
  [[ -f "${helpers}/_reindex_on_edit.sh" ]] || helpers="$(dirname "$0")"
  # shellcheck source=/dev/null
  source "${helpers}/_reindex_on_edit.sh" 2>/dev/null || return 0
  # Deduplicated: a path both committed since the marker and still dirty
  # would otherwise be dispatched twice.
  local -a unique=()
  while IFS= read -r -d '' rel; do unique+=("$rel"); done < <(printf '%s\0' ${changed[@]+"${changed[@]}"} | sort -zu)
  cos_reindex_catchup warn-graph-empty "$head" "$head_marker" ${unique[@]+"${unique[@]}"}
  cos_log_hook warn-graph-empty catchup "paths=${#unique[@]}" || true
}

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
  graph_catchup
fi

# Bounded log file
if [[ -f "$LOG_FILE" ]]; then
  LINES=$(wc -l < "$LOG_FILE" 2>/dev/null || echo 0)
  if (( LINES > 200 )); then
    tail -n 200 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
  fi
fi

exit 0
