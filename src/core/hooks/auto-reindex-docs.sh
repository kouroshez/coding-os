#!/usr/bin/env bash
# PostToolUse hook: after a Write/Edit of a .md file, refresh its doc-search
# chunks (the docs layer of graph_os.tools.reindex_dispatch) so cos_doc_search
# answers from the edited text without a manual `make docs-index`. Owned by the
# docs module; the file's graph nodes are auto-reindex-graph.sh, owned by the
# graph module. Fire-and-forget and fail-open: the worker runs in the background
# and its errors land in $COS_STATE_DIR/.reindex-errors.log.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
# Without the env there is no state dir or Python to reindex with.
command -v cos_read_stdin_bounded >/dev/null 2>&1 || exit 0
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
if [[ "$FILE_PATH" != *.md ]]; then
  exit 0
fi

# A consumer's hooks dir holds one symlink per hook; the shared body sits next
# to the real file, which _cos_helpers_dir walks the symlink back to.
_HOOKS_REAL="$(dirname "$(_cos_helpers_dir 2>/dev/null)")"
[[ -f "${_HOOKS_REAL}/_reindex_on_edit.sh" ]] || _HOOKS_REAL="$(dirname "$0")"
# shellcheck source=/dev/null
if ! source "${_HOOKS_REAL}/_reindex_on_edit.sh" 2>/dev/null; then
  cos_log_hook auto-reindex-docs skip "reason=reindex_body_missing"
  exit 0
fi
cos_reindex_on_edit auto-reindex-docs docs "$FILE_PATH"
exit 0
