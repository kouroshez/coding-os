#!/usr/bin/env bash
# PostToolUse hook (Phase H): after Write or Edit, if the file belongs to a
# rag-config.yaml source, fire a single-file re-index in background so
# cos_doc_search stays fresh without the user running `make docs-index`.
#
# Design:
#   - Fire-and-forget: worker forks to background; the Write/Edit returns
#     immediately. Worst-case freshness lag = one embed cycle (~200 ms).
#   - Scoped: only matched files trigger re-index. Edits to playbooks /
#     governance / code are no-ops.
#   - Fail-open: any missing dep (no rag-config, no rag extras, no db)
#     is a silent skip. Errors land in $COS_STATE_DIR/.reindex-errors.log
#     (bounded, ~200 lines).
#   - Adapter-agnostic: reads COS_STATE_DIR / COS_DB_PATH from cos-env.sh
#     so both Claude and Codex sessions behave identically.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

# Only markdown goes into RAG (matches rag-config.yaml scope).
case "$FILE_PATH" in
  *.md) ;;
  *) exit 0 ;;
esac

cos_log_hook auto-reindex-docs fire "file=${FILE_PATH}"

# Resolve project_root from COS_PROJECT_ROOT or cwd.
PROJECT_ROOT="${COS_PROJECT_ROOT:-$PWD}"
CONFIG_PATH="${COS_RAG_CONFIG:-${PROJECT_ROOT}/.coding-os/rag-config.yaml}"

# If no rag-config in this project, silently skip (consumer project that
# hasn't enabled RAG — nothing to index).
if [[ ! -f "$CONFIG_PATH" ]]; then
  cos_log_hook auto-reindex-docs skip "reason=no_rag_config"
  exit 0
fi

# Locate the thinking-os module directory. core/ vs .claude/ depending on
# adapter layout; fall back to either so meta-project + consumer both work.
TOS_DIR=""
for candidate in \
  "${COS_BRAIN_DIR:-}" \
  "$(dirname "$0")/../thinking-os" \
  "${PROJECT_ROOT}/core/thinking-os" \
  "${PROJECT_ROOT}/.claude/thinking-os"; do
  if [[ -n "$candidate" && -f "${candidate}/doc_indexer.py" ]]; then
    TOS_DIR="$candidate"
    break
  fi
done

if [[ -z "$TOS_DIR" ]]; then
  cos_log_hook auto-reindex-docs skip "reason=no_brain_dir"
  exit 0
fi

ERR_LOG="${COS_STATE_DIR}/.reindex-errors.log"
mkdir -p "$(dirname "$ERR_LOG")"

# Fire the re-index in background so the Write/Edit returns immediately.
# Python does the scope check (matches rag-config source), so shell just
# hands off the path.
(
  python3 -c "
import os, sys
from pathlib import Path
sys.path.insert(0, '${TOS_DIR}')
try:
    from db import init_db
    from doc_indexer import index_single_file

    project_root = Path('${PROJECT_ROOT}').resolve()
    config_path = Path('${CONFIG_PATH}').resolve()
    file_path = Path('${FILE_PATH}').resolve()

    db_path = os.environ.get('COS_DB_PATH') or str(project_root / '.coding-os' / 'thinking-os.db')
    conn = init_db(db_path)
    try:
        result = index_single_file(
            conn, file_path,
            project_root=project_root,
            config_path=config_path,
        )
        status = result.get('status', 'unknown')
        # Only surface non-no-op outcomes to the log; unscoped is silent.
        if status in ('reindexed', 'deleted', 'error'):
            print(f'[auto-reindex] {status}: {result.get(\"file\")} '
                  f'(+{result.get(\"new_chunks\", 0)} / -{result.get(\"deleted_chunks\", 0)})',
                  file=sys.stderr)
    finally:
        conn.close()
except Exception as exc:  # noqa: BLE001 — fire-and-forget chokepoint
    print(f'[auto-reindex] ERROR: {type(exc).__name__}: {exc}', file=sys.stderr)
" 2>>"$ERR_LOG" &
) &

# Trim error log to last 200 lines so it never balloons.
if [[ -f "$ERR_LOG" ]]; then
  LINES=$(wc -l < "$ERR_LOG" 2>/dev/null || echo 0)
  if (( LINES > 200 )); then
    tail -n 200 "$ERR_LOG" > "${ERR_LOG}.tmp" && mv "${ERR_LOG}.tmp" "$ERR_LOG"
  fi
fi

cos_log_hook auto-reindex-docs dispatched "file=${FILE_PATH}"
exit 0
