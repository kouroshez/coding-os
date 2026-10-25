#!/usr/bin/env bash
# SessionStart hook: per-agent state hygiene — prunes stale markers, traces and
# orphan panel dirs, then runs the WAL guard. The id is historical: it also
# used to decay the DB-backed pattern memory, which was removed 2026-10-24.
# Fire-and-forget — never blocks session start.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

COS_STATE_DIR="${COS_STATE_DIR:-.coding-os}"
COS_DB_PATH="${COS_DB_PATH:-$COS_STATE_DIR/coding-os.db}"

cos_log_hook auto-brain-decay fire

NOW_TS=$(date +%s)

# ---------------------------------------------------------------------------
# Stale state-file GC.
#
# WHY
#   Session-scoped markers under $COS_AGENT_DIR (.thinking_os-gate,
#   .doc-anchor, .roles, .role, .situation, .active-skill,
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
# Runs on every session start — even fresh installs without a DB benefit
# from the cleanup, and the GC is cheap enough (≤20 stat calls) to run
# inline. Errors silently ignored.
# ---------------------------------------------------------------------------
if [[ -d "${COS_AGENT_DIR:-}" ]]; then
  for marker in .thinking_os-gate .doc-anchor .roles .role \
                .situation .active-skill .zoom-checkpoint .rename-plan \
                .graph-context .task-current; do
    f="$COS_AGENT_DIR/$marker"
    if [[ -f "$f" ]]; then
      mtime=$(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f" 2>/dev/null || echo 0)
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
        hb=$(stat -c %Y "$heartbeat_file" 2>/dev/null || stat -f %m "$heartbeat_file" 2>/dev/null || echo 0)
        [[ "$hb" -gt 0 ]] && orphan_age=$((NOW_TS - hb))
      else
        # No heartbeat either — use dir mtime.
        mt=$(stat -c %Y "$panel_dir" 2>/dev/null || stat -f %m "$panel_dir" 2>/dev/null || echo 0)
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

# DB absent (fresh install) → nothing for the WAL guard to check.
if [ ! -f "$COS_DB_PATH" ]; then
  cos_log_hook auto-brain-decay skip "reason=no_db"
  exit 0
fi

# ---------------------------------------------------------------------------
# WAL guard.
#
# WHY
#   `journal_size_limit` (thinking_os/_db_pool.py) caps the -wal at each WAL
#   restart, which is the real fix. It cannot help when the checkpoint that
#   precedes that restart is blocked by a long-lived reader holding a
#   snapshot — the shape that grew the -wal to 59 GB beside a 342 MB database
#   and took the boot volume to 92% full. This forces TRUNCATE and, when a
#   reader blocks it, names the PIDs so the operator can clear the blocker.
#
# POLICY
#   - Runs on every session start: a runaway WAL is a disk-space
#     emergency.
#   - The helper stats the -wal first and returns without opening the DB
#     when it is under COS_WAL_GUARD_MB (default 50 — the same number
#     `cos doctor` warns at), so the healthy path costs one stat call.
#   - Fail-open: hygiene sweep, never a correctness gate.
# ---------------------------------------------------------------------------
COS_WAL_GUARD_MB="${COS_WAL_GUARD_MB:-50}"
if command -v _cos_helpers_dir >/dev/null 2>&1; then
  WAL_GUARD_HELPER="$(_cos_helpers_dir)/wal_guard.py"
  if [ -f "$WAL_GUARD_HELPER" ]; then
    # stdout is the machine summary; stderr is left alone so the operator
    # report reaches the session-start stderr channel unfiltered.
    WAL_GUARD_SUMMARY=$(python3 "$WAL_GUARD_HELPER" \
      "$COS_DB_PATH" "$((COS_WAL_GUARD_MB * 1024 * 1024))") || WAL_GUARD_SUMMARY=""
    if [ -n "$WAL_GUARD_SUMMARY" ]; then
      cos_log_hook auto-brain-decay wal-guard "$WAL_GUARD_SUMMARY"
    fi
  fi
fi

exit 0
