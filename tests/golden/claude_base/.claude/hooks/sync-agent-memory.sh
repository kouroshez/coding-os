#!/usr/bin/env bash
# Stop hook: mirror Trusted lessons into .agents/memory/MEMORY.md and harvest
# foreign notes back into the DB (hash-deduped). Fail-open observability.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
command -v cos_log_hook >/dev/null 2>&1 || cos_log_hook() { :; }

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "${CLAUDE_PROJECT_DIR:-$PWD}")"
REPO_MEM="$REPO_ROOT/.agents/memory"
DB_PATH="${COS_DB_PATH:-$REPO_ROOT/.coding-os/coding-os.db}"

[ -d "$REPO_MEM" ] || exit 0
[ -f "$DB_PATH" ] || exit 0

HELPER="$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")/agent_memory_sync.py"
[ -f "$HELPER" ] || exit 0

cos_log_hook sync-agent-memory fire "dir=$REPO_MEM" || true
python3 "$HELPER" "$DB_PATH" "$REPO_MEM" 2>/dev/null || true
exit 0
