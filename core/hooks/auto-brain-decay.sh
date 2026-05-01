#!/usr/bin/env bash
# SessionStart hook: run confidence decay on learned_patterns once per 24 h.
#
# Rationale: without a scheduler, pattern confidence never fades — stale
# rules keep surfacing in cos_learn_suggest long after they stopped
# matching reality. Ebbinghaus decay is applied by
# core/thinking_os/decay.py; this hook just debounces it so we don't
# re-run on every session start.
#
# Debounce file: $COS_STATE_DIR/.last-decay (unix ts). 24 h window.
# Fire-and-forget — never blocks session start.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
COS_STATE_DIR="${COS_STATE_DIR:-.coding-os}"
COS_DB_PATH="${COS_DB_PATH:-$COS_STATE_DIR/coding-os.db}"

cos_log_hook auto-brain-decay fire

NOW_TS=$(date +%s)
LAST_RUN_FILE="$COS_STATE_DIR/.last-decay"
DEBOUNCE_SECONDS=$((24 * 60 * 60))

# ---------------------------------------------------------------------------
# Stale state-file GC.
#
# WHY
#   Session-scoped markers under $COS_AGENT_DIR (.thinking_os-gate,
#   .doc-anchor, .memory-check, .roles, .role, .situation, .active-skill,
#   .zoom-checkpoint, .rename-plan, .graph-context, .task-current) are
#   bound to a single session. Old sessions' markers stay on disk forever
#   unless something reaps them. Over months of dogfooding the agent dir
#   accumulates hundreds-thousands of stale dotfiles and traces/*.jsonl
#   blobs, polluting `ls`, slowing `find`, and confusing debug runs.
#
# POLICY
#   - Marker dotfiles older than 7 days → deleted.
#   - traces/*.jsonl older than 30 days → deleted.
#   - Bounded to ${COS_AGENT_DIR} only (never touches the shared
#     COS_STATE_DIR root). Symlinks ignored.
#
# Runs UNCONDITIONALLY before the DB-debounced decay below — even fresh
# installs without a DB benefit from the cleanup, and the GC is cheap
# enough (≤20 stat calls) to run inline. Errors silently ignored.
# ---------------------------------------------------------------------------
if [[ -d "${COS_AGENT_DIR:-}" ]]; then
  for marker in .thinking_os-gate .doc-anchor .memory-check .roles .role \
                .situation .active-skill .zoom-checkpoint .rename-plan \
                .graph-context .task-current; do
    f="$COS_AGENT_DIR/$marker"
    if [[ -f "$f" ]]; then
      mtime=$(stat -f %m "$f" 2>/dev/null || stat -c %Y "$f" 2>/dev/null || echo 0)
      if [[ "$mtime" -gt 0 ]] && [[ $((NOW_TS - mtime)) -gt $((7 * 24 * 60 * 60)) ]]; then
        rm -f "$f" 2>/dev/null || true
        cos_log_hook auto-brain-decay gc "removed=${marker} age_s=$((NOW_TS - mtime))"
      fi
    fi
  done
  if [[ -d "$COS_AGENT_DIR/traces" ]]; then
    find "$COS_AGENT_DIR/traces" -maxdepth 1 -type f -name '*.jsonl' \
      -mtime +30 -delete 2>/dev/null || true
  fi
fi

# DB absent (fresh install, no patterns yet) → skip pattern decay (GC above
# already ran).
if [ ! -f "$COS_DB_PATH" ]; then
  cos_log_hook auto-brain-decay skip "reason=no_db"
  exit 0
fi

if [ -f "$LAST_RUN_FILE" ]; then
  LAST_TS=$(cat "$LAST_RUN_FILE" 2>/dev/null | tr -d '[:space:]')
  if [ -n "$LAST_TS" ] && [ "$LAST_TS" -gt 0 ] 2>/dev/null; then
    DELTA=$((NOW_TS - LAST_TS))
    if [ "$DELTA" -lt "$DEBOUNCE_SECONDS" ]; then
      cos_log_hook auto-brain-decay skip "reason=debounced age_s=${DELTA}"
      exit 0
    fi
  fi
fi

# Resolve the decay script path across meta and consumer layouts.
DECAY_SCRIPT=""
for CAND in \
  "$(dirname "$0")/../thinking_os/decay.py" \
  ".coding-os/thinking_os/decay.py" \
  "core/thinking_os/decay.py"; do
  if [ -f "$CAND" ]; then
    DECAY_SCRIPT="$CAND"
    break
  fi
done
if [ -z "$DECAY_SCRIPT" ]; then
  cos_log_hook auto-brain-decay skip "reason=script_not_found"
  exit 0
fi

# Fire-and-forget — decay.py is bounded (ms per pattern, no I/O beyond
# the DB) but we still run in the background so SessionStart latency is
# untouched.
(
  COS_DB_PATH="$COS_DB_PATH" \
  timeout 10 python3 "$DECAY_SCRIPT" > /dev/null 2>&1 \
    && echo "$NOW_TS" > "$LAST_RUN_FILE"
) &

exit 0

exit 0
