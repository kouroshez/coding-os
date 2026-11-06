#!/usr/bin/env bash
# wal-guard.sh — Stop hook.
#
# Forces a WAL checkpoint when coding-os.db-wal has outgrown its budget. The
# connection cap (WAL_SIZE_LIMIT_BYTES in thinking_os/_db_pool.py) only takes
# effect at a checkpoint, so it cannot reach the one case that matters: a
# long-lived reader holding a snapshot blocks every checkpoint and the -wal
# grows unbounded. That is how it reached 59 GB beside a 342 MB database.
# Fail-open: never blocks the Stop, always exits 0.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook wal-guard enter || true

[ -f "${COS_DB_PATH:-}" ] || exit 0

# Threshold sits above the 32 MB connection cap so a healthy WAL that is simply
# mid-cycle never triggers a checkpoint, and below the 50 MB budget `cos doctor`
# warns at, so the guard fires before the operator-visible warning does.
WAL_GUARD_THRESHOLD_BYTES=${WAL_GUARD_THRESHOLD_BYTES:-41943040}

python3 "$(dirname "$0")/_helpers/wal_guard.py" \
  "$COS_DB_PATH" "$WAL_GUARD_THRESHOLD_BYTES" 2>/dev/null || true

cos_log_hook wal-guard ok || true
exit 0
