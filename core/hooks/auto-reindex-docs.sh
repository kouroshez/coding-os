#!/usr/bin/env bash
# PostToolUse hook (Phase H + Phase I): after Write/Edit, re-index the
# touched file into both the docs RAG layer AND the graph_os structural
# layer so cos_doc_search and cos_graph_* stay fresh without manual
# `make docs-index` / `cos graph-reindex` runs.
#
# Design:
#   - Fire-and-forget: worker forks to background; Write/Edit returns
#     immediately. Worst-case freshness lag = one dispatcher cycle.
#   - Dispatcher is Python (`graph_os.tools.reindex_dispatch`) — Python
#     owns the scope check + per-suffix extractor chain; shell just
#     routes paths.
#   - Scoped: docs layer handles only .md; graph layer handles every
#     suffix the extractor map knows (.py/.ts/.tsx/.sh/.yaml/.md/.go).
#   - Fail-open: any missing dep is a silent skip. Errors land in
#     $COS_STATE_DIR/.reindex-errors.log (bounded, ~200 lines).
#   - Adapter-agnostic: reads COS_STATE_DIR / COS_DB_PATH from cos-env.sh.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

case "$FILE_PATH" in
  *.md|*.py|*.ts|*.tsx|*.sh|*.yaml|*.yml|*.go) ;;
  *) exit 0 ;;
esac

cos_log_hook auto-reindex-docs fire "file=${FILE_PATH}"

# ── Debounce (D3) ────────────────────────────────────────────────────
# Coalesce rapid successive writes on the same path within a 3-second
# window to prevent N parallel background workers when an agent edits
# a file in quick succession. Strategy: write a per-path lockfile with
# the current timestamp; skip if the file was touched in the last 3 s.
_DEBOUNCE_TTL=3
_STATE_BASE="${COS_STATE_DIR:-${PWD}/.coding-os}"
_SAFE_PATH=$(printf '%s' "$FILE_PATH" | tr '/' '_' | tr ' ' '_')
_DEBOUNCE_FILE="${_STATE_BASE}/.reindex-debounce-${_SAFE_PATH}"
_NOW=$(date +%s)
if [[ -f "$_DEBOUNCE_FILE" ]]; then
  _LAST=$(cat "$_DEBOUNCE_FILE" 2>/dev/null || echo 0)
  if (( _NOW - _LAST < _DEBOUNCE_TTL )); then
    cos_log_hook auto-reindex-docs skip "reason=debounced file=${FILE_PATH##*/}"
    exit 0
  fi
fi
mkdir -p "$(dirname "$_DEBOUNCE_FILE")"
echo "$_NOW" > "$_DEBOUNCE_FILE"

PROJECT_ROOT="${COS_PROJECT_ROOT:-$PWD}"
CORE_DIR=""
for candidate in \
  "${COS_CORE_DIR:-}" \
  "$(dirname "$0")/.." \
  "${PROJECT_ROOT}/core"; do
  if [[ -n "$candidate" && -d "${candidate}/graph_os" ]]; then
    CORE_DIR="$(cd "$candidate" && pwd)"
    break
  fi
done

if [[ -z "$CORE_DIR" ]]; then
  cos_log_hook auto-reindex-docs skip "reason=no_core_dir"
  exit 0
fi

ERR_LOG="${COS_STATE_DIR:-${PROJECT_ROOT}/.coding-os}/.reindex-errors.log"
mkdir -p "$(dirname "$ERR_LOG")"

# Fire the re-index in background via the unified Python dispatcher.
# Stdout is muted (hook must stay quiet); stderr → error log.
(
  "${COS_PYTHON:-python3}" -c "
import os, sys
sys.path.insert(0, '${CORE_DIR}')
sys.path.insert(0, '${CORE_DIR}/thinking_os')
try:
    from graph_os.tools.reindex_dispatch import dispatch
    report = dispatch(
        '${FILE_PATH}',
        project_root='${PROJECT_ROOT}',
        db_path=os.environ.get('COS_DB_PATH'),
    )
    if report.get('status') != 'skipped':
        print(f\"[auto-reindex] {report['status']}: {report['path']} \"
              f\"({report['duration_ms']}ms, layers={list(report['layers'].keys())})\",
              file=sys.stderr)
except Exception as exc:
    print(f'[auto-reindex] ERROR: {type(exc).__name__}: {exc}', file=sys.stderr)
" 2>>"$ERR_LOG" &
) &

if [[ -f "$ERR_LOG" ]]; then
  LINES=$(wc -l < "$ERR_LOG" 2>/dev/null || echo 0)
  if (( LINES > 200 )); then
    tail -n 200 "$ERR_LOG" > "${ERR_LOG}.tmp" && mv "${ERR_LOG}.tmp" "$ERR_LOG"
  fi
fi

cos_log_hook auto-reindex-docs dispatched "file=${FILE_PATH}"
exit 0
