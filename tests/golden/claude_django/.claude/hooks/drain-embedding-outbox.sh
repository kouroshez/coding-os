#!/usr/bin/env bash
# drain-embedding-outbox.sh — Stop hook.
#
# Drains the embedding_outbox (hot-path-skipped embeddings, Wave 4) off the
# interactive path so observations captured during the session get their
# semantic vectors without ever blocking an Edit. Fail-open: never blocks the
# Stop. The helper fast-paths out (zero model load) when the outbox is empty.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook drain-embedding-outbox enter || true

[ -f "${COS_DB_PATH:-}" ] || exit 0

python3 "$(dirname "$0")/_helpers/drain_embedding_outbox.py" 2>/dev/null || true

cos_log_hook drain-embedding-outbox ok || true
exit 0
