#!/usr/bin/env bash
# PostToolUse hook: after a Write/Edit of a .md file, refresh its doc-search
# chunks (the docs layer of graph_os.tools.reindex_dispatch) so cos_doc_search
# answers from the edited text without a manual `make docs-index`. Owned by the
# docs module; the file's graph nodes are auto-reindex-graph.sh, owned by the
# graph module. Fire-and-forget and fail-open: the worker runs in the background
# and its errors land in $COS_STATE_DIR/.reindex-errors.log.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
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

source "$(dirname "$0")/_reindex_on_edit.sh" 2>/dev/null || exit 0
cos_reindex_on_edit auto-reindex-docs docs "$FILE_PATH"
exit 0
