#!/usr/bin/env bash
# Stop hook — rotate trace JSONL files (age-based) and unbounded logs
# (size-based copytruncate).
#
# Trace targets: $COS_AGENT_DIR/traces/*.jsonl
#   - gzip files older than COS_TRACE_GZIP_AGE_DAYS (default 3)
#   - delete (gz or jsonl) older than COS_TRACE_DELETE_AGE_DAYS (default 30)
#
# Log targets: $COS_STATE_DIR/.{mcp,cos,hooks}.log + .cos.log.jsonl
#   - when file >= COS_LOG_ROTATE_SIZE_BYTES (default 5_242_880 = 5MB):
#     gzip-copy → archive .<name>.<ts>.gz, then truncate original in-place
#     (server fds keep writing; classic logrotate copytruncate)
#   - keep most-recent COS_LOG_ROTATE_KEEP archives (default 3), delete older
#
# Fire-and-forget; bounded; never blocks the caller.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

GZIP_AGE_DAYS="${COS_TRACE_GZIP_AGE_DAYS:-3}"
DELETE_AGE_DAYS="${COS_TRACE_DELETE_AGE_DAYS:-30}"
LOG_ROTATE_SIZE_BYTES="${COS_LOG_ROTATE_SIZE_BYTES:-5242880}"
LOG_ROTATE_KEEP="${COS_LOG_ROTATE_KEEP:-3}"

GZIPPED=0
DELETED=0
LOGS_ROTATED=0

# ── traces (age-based) ─────────────────────────────────────────────
TRACE_DIR="${COS_AGENT_DIR:-}/traces"
if [[ -n "${COS_AGENT_DIR:-}" ]] && [[ -d "$TRACE_DIR" ]]; then
  case "$TRACE_DIR" in
    *"/.coding-os/"*"/traces")
      while IFS= read -r -d '' f; do
        if gzip -q -- "$f" 2>/dev/null; then
          GZIPPED=$((GZIPPED + 1))
        fi
      done < <(find "$TRACE_DIR" -maxdepth 1 -type f -name '*.jsonl' \
                    -mtime "+$GZIP_AGE_DAYS" -print0 2>/dev/null)

      while IFS= read -r -d '' f; do
        if rm -f -- "$f" 2>/dev/null; then
          DELETED=$((DELETED + 1))
        fi
      done < <(find "$TRACE_DIR" -maxdepth 1 -type f \
                    \( -name '*.jsonl' -o -name '*.jsonl.gz' \) \
                    -mtime "+$DELETE_AGE_DAYS" -print0 2>/dev/null)
      ;;
  esac
fi

# ── logs (size-based copytruncate) ─────────────────────────────────
STATE_DIR="${COS_STATE_DIR:-}"
if [[ -n "$STATE_DIR" ]] && [[ -d "$STATE_DIR" ]]; then
  case "$STATE_DIR" in
    *"/.coding-os")
      ts=$(date -u +%Y%m%dT%H%M%SZ)
      for name in .mcp.log .cos.log .cos.log.jsonl .hooks.log; do
        f="$STATE_DIR/$name"
        [[ -f "$f" ]] || continue
        size=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null || echo 0)
        if [[ "$size" -ge "$LOG_ROTATE_SIZE_BYTES" ]]; then
          archive="$STATE_DIR/${name}.${ts}.gz"
          if gzip -c -- "$f" > "$archive" 2>/dev/null; then
            : > "$f"
            LOGS_ROTATED=$((LOGS_ROTATED + 1))
          fi
        fi
        # Trim old archives — keep newest $LOG_ROTATE_KEEP, delete rest.
        old=$(ls -1t "$STATE_DIR/${name}".*.gz 2>/dev/null | tail -n +$((LOG_ROTATE_KEEP + 1)) || true)
        if [[ -n "$old" ]]; then
          echo "$old" | xargs rm -f -- 2>/dev/null || true
        fi
      done
      ;;
  esac
fi

cos_log_hook auto-trace-rotate fire \
  "gzipped=${GZIPPED} deleted=${DELETED} logs_rotated=${LOGS_ROTATED}"

exit 0
