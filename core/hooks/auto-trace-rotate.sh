#!/usr/bin/env bash
# Stop hook — rotate old trace JSONL files.
#
# Targets: $COS_AGENT_DIR/traces/*.jsonl
# Action:
#   - gzip files older than COS_TRACE_GZIP_AGE_DAYS (default 3)
#   - delete (gz or jsonl) older than COS_TRACE_DELETE_AGE_DAYS (default 30)
#
# Fire-and-forget; bounded; never blocks the caller.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

GZIP_AGE_DAYS="${COS_TRACE_GZIP_AGE_DAYS:-3}"
DELETE_AGE_DAYS="${COS_TRACE_DELETE_AGE_DAYS:-30}"

TRACE_DIR="${COS_AGENT_DIR:-}/traces"
if [[ -z "${COS_AGENT_DIR:-}" ]] || [[ ! -d "$TRACE_DIR" ]]; then
  exit 0
fi

# Sanity guard: refuse to operate outside the project state dir.
case "$TRACE_DIR" in
  *"/.coding-os/"*"/traces") ;;
  *) exit 0 ;;
esac

GZIPPED=0
DELETED=0

# Compress old uncompressed JSONL.
while IFS= read -r -d '' f; do
  if gzip -q -- "$f" 2>/dev/null; then
    GZIPPED=$((GZIPPED + 1))
  fi
done < <(find "$TRACE_DIR" -maxdepth 1 -type f -name '*.jsonl' \
              -mtime "+$GZIP_AGE_DAYS" -print0 2>/dev/null)

# Delete very old archives or jsonl.
while IFS= read -r -d '' f; do
  if rm -f -- "$f" 2>/dev/null; then
    DELETED=$((DELETED + 1))
  fi
done < <(find "$TRACE_DIR" -maxdepth 1 -type f \
              \( -name '*.jsonl' -o -name '*.jsonl.gz' \) \
              -mtime "+$DELETE_AGE_DAYS" -print0 2>/dev/null)

cos_log_hook auto-trace-rotate fire "gzipped=${GZIPPED} deleted=${DELETED} dir=${TRACE_DIR}"

exit 0
