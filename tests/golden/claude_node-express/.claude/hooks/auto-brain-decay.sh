#!/usr/bin/env bash
# SessionStart hook: run confidence decay on learned_patterns once per 24 h.
#
# Rationale: without a scheduler, pattern confidence never fades — stale
# rules keep surfacing in cos_learn_suggest long after they stopped
# matching reality. Ebbinghaus decay is applied by
# src/core/thinking_os/decay.py; this hook just debounces it so we don't
# re-run on every session start.
#
# Debounce file: <db-dir>/.last-decay (unix ts), shared with decay.py. 24 h window.
# Fire-and-forget — never blocks session start.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

COS_STATE_DIR="${COS_STATE_DIR:-.coding-os}"
COS_DB_PATH="${COS_DB_PATH:-$COS_STATE_DIR/coding-os.db}"

cos_log_hook auto-brain-decay fire

NOW_TS=$(date +%s)
# Align with decay.py::run_decay_locked, which marks/throttles + flocks on
# `<db-dir>/.last-decay`. When COS_DB_PATH sits outside
# COS_STATE_DIR the two diverged — this hook would re-run decay the nightly
# job just throttled. Derive from the DB dir so both share one marker + lock.
LAST_RUN_FILE="$(dirname "$COS_DB_PATH")/.last-decay"
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

# ---------------------------------------------------------------------------
# Per-panel orphan GC.
#
# WHY
#   Each panel of the same agent gets its own $COS_AGENT_DIR/panels/<panel-id>/
#   subdir (see docs/engineering/state-files.md § per-panel isolation). When
#   a panel terminates without firing Stop (laptop sleeps, agent crashes,
#   tab killed), its subdir lingers. Without GC, repeated dogfooding leaves
#   hundreds of dead panel dirs.
#
# POLICY
#   - panels/<id>/ dirs whose heartbeat is older than COS_PANEL_GC_TTL
#     (default 24 h) → entire subdir removed.
#   - Live panels (heartbeat fresh) are never touched, even if old; the
#     heartbeat file is rewritten by cos-env.sh on every hook fire so any
#     active panel will pass the freshness check.
#   - The current panel is explicitly excluded ($COS_PANEL_DIR) so the
#     running session never garbage-collects itself mid-flight.
#   - Fail-open: any error during GC is swallowed (this is a hygiene
#     sweep, never a correctness gate).
# ---------------------------------------------------------------------------
COS_PANEL_GC_TTL="${COS_PANEL_GC_TTL:-86400}"        # 24 h for real panels
COS_PANEL_GC_ORPHAN_TTL="${COS_PANEL_GC_ORPHAN_TTL:-3600}"  # 1 h for no-session orphans
if [[ -d "${COS_AGENT_DIR:-}/panels" ]]; then
  for panel_dir in "${COS_AGENT_DIR}/panels"/*/; do
    [[ -d "$panel_dir" ]] || continue
    panel_dir="${panel_dir%/}"
    if [[ "$panel_dir" == "$COS_PANEL_DIR" ]]; then
      continue
    fi
    heartbeat_file="${panel_dir}/heartbeat"
    session_id_file="${panel_dir}/session-id"
    # Tier 1 — orphan: no session-id was ever written. The only thing
    # that writes session-id into a panel dir is
    # cos_panel_upgrade_from_payload (called by session-context.sh on a
    # real Claude/Codex hook fire). A panel dir without session-id was
    # created by a stray bash invocation (test, sourced cos-env.sh, etc.)
    # whose PPID happened to hash to a unique panel-id — never a real
    # agent session. Reap aggressively (default 1 h) to keep the panels/
    # subtree from growing without bound during test runs and shell work.
    if [[ ! -s "$session_id_file" ]]; then
      orphan_age=0
      if [[ -f "$heartbeat_file" ]]; then
        hb=$(stat -f %m "$heartbeat_file" 2>/dev/null || stat -c %Y "$heartbeat_file" 2>/dev/null || echo 0)
        [[ "$hb" -gt 0 ]] && orphan_age=$((NOW_TS - hb))
      else
        # No heartbeat either — use dir mtime.
        mt=$(stat -f %m "$panel_dir" 2>/dev/null || stat -c %Y "$panel_dir" 2>/dev/null || echo 0)
        [[ "$mt" -gt 0 ]] && orphan_age=$((NOW_TS - mt))
      fi
      if [[ "$orphan_age" -gt "$COS_PANEL_GC_ORPHAN_TTL" ]]; then
        rm -rf "$panel_dir" 2>/dev/null || true
        cos_log_hook auto-brain-decay gc "removed_orphan_panel=$(basename "$panel_dir") age_s=${orphan_age}"
      fi
      continue
    fi
    # Tier 2 — stale real panel: heartbeat older than 24 h.
    if [[ -f "$heartbeat_file" ]]; then
      hb=$(stat -f %m "$heartbeat_file" 2>/dev/null || stat -c %Y "$heartbeat_file" 2>/dev/null || echo 0)
      if [[ "$hb" -gt 0 ]] && [[ $((NOW_TS - hb)) -lt "$COS_PANEL_GC_TTL" ]]; then
        continue  # panel is live
      fi
    fi
    rm -rf "$panel_dir" 2>/dev/null || true
    cos_log_hook auto-brain-decay gc "removed_panel=$(basename "$panel_dir")"
  done
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
  "src/core/thinking_os/decay.py"; do
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
  python3 "$DECAY_SCRIPT" > /dev/null 2>&1 \
    && echo "$NOW_TS" > "$LAST_RUN_FILE"
) &

exit 0

exit 0
