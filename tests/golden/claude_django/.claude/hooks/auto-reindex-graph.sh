#!/usr/bin/env bash
# PostToolUse hook: after a Write/Edit, re-extract the touched file's nodes and
# edges (the graph layer of graph_os.tools.reindex_dispatch) so cos_graph_*
# answers from the edited code without a manual `cos graph-reindex`. Owned by
# the graph module; an edited doc's search chunks are auto-reindex-docs.sh,
# owned by the docs module. Fire-and-forget and fail-open: the worker runs in
# the background and its errors land in $COS_STATE_DIR/.reindex-errors.log.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

# Skips the Python start for a file no extractor reads; it must admit every
# suffix the dispatcher routes, which test_reindex_hook_suffixes.py holds it to.
case "$FILE_PATH" in
  *.md|*.mdx|*.py|*.ts|*.tsx|*.mts|*.cts|*.js|*.jsx|*.mjs|*.cjs|*.astro|*.sh|*.bash|*.zsh|*.yaml|*.yml|*.go|*.php|*.json|*.toml|*.rs|*.rb|*.java|*.c|*.h|*.cc|*.cpp|*.cxx|*.hpp|*.hh|*.cs|*.scala|*.kt|*.kts|*.lua) ;;
  # An extensionless file may be a shebang script; the dispatcher reads its #! line.
  *) if [[ "${FILE_PATH##*/}" == *.* ]]; then exit 0; fi ;;
esac

source "$(dirname "$0")/_reindex_on_edit.sh" 2>/dev/null || exit 0
cos_reindex_on_edit auto-reindex-graph graph "$FILE_PATH"
exit 0
