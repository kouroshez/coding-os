#!/usr/bin/env bash
# enforce-graph-first-read.sh (Phase I.15)
#
# PreToolUse — Read on a load-bearing meta-repo file.
# Warn (or block in strict mode) when the agent tries to Read a
# load-bearing file BEFORE having called any cos_graph_* tool in this
# session. Closes the gap where graph nudges are easy to ignore by
# reaching for Read directly.
#
# Marker tracked: $COS_AGENT_DIR/.graph-call-seen — touched by the MCP
# tool side (graph_os.tools.graph._record_call) on first cos_graph_*
# call. If the marker exists, this hook is a no-op.
#
# Default: warn. Promote: COS_ENFORCE_GRAPH_FIRST=strict.
# Disable:  COS_ENFORCE_GRAPH_FIRST=off
set -eu

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook enforce-graph-first-read enter || true

MODE="${COS_ENFORCE_GRAPH_FIRST:-1}"
if [[ "$MODE" == "off" || "$MODE" == "0" ]]; then
  cos_log_hook enforce-graph-first-read disabled || true
  exit 0
fi

PAYLOAD="$(cat 2>/dev/null || true)"
TOOL=$(printf '%s' "$PAYLOAD" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
if [[ "$TOOL" != "Read" ]]; then
  exit 0
fi

FILE_PATH=$(printf '%s' "$PAYLOAD" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

# Reuse the same enforce_context_on glob list as enforce-graph-context.
CONFIG="${COS_STATE_DIR:-.coding-os}/rag-config.yaml"
[[ -f "$CONFIG" ]] || CONFIG="$(pwd)/.coding-os/rag-config.yaml"
if [[ ! -f "$CONFIG" ]]; then
  exit 0
fi

_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
  _dir="$(cd -P "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ "$_src" != /* ]] && _src="$_dir/$_src"
done
HSRC="$(cd -P "$(dirname "$_src")" && pwd)"
unset _src _dir
HELPER="${HSRC}/_helpers/graph_context_match.py"
if [[ ! -f "$HELPER" ]]; then
  exit 0
fi
MATCHED="$(python3 "$HELPER" "$CONFIG" "$FILE_PATH" 2>/dev/null || echo no)"
if [[ "$MATCHED" != "yes" ]]; then
  exit 0
fi

# Has any cos_graph_* call landed this session?
GRAPH_SEEN="${COS_AGENT_DIR:-.coding-os/claude}/.graph-call-seen"
if [[ -f "$GRAPH_SEEN" ]]; then
  cos_log_hook enforce-graph-first-read ok || true
  exit 0
fi

# Also accept the per-file marker — agent may have called
# cos_graph_context for THIS specific file already.
SHA="$(printf '%s' "$FILE_PATH" | sha1sum 2>/dev/null | awk '{print $1}')"
PER_FILE_MARKER="${COS_AGENT_DIR:-.coding-os/claude}/.graph-context-${SHA}"
if [[ -f "$PER_FILE_MARKER" ]]; then
  exit 0
fi

MSG="Reading load-bearing file ($FILE_PATH) without a prior cos_graph_* call this session.
  Why this matters: structural questions (callers, blast radius, rename, contracts) belong on the graph layer, not file Read.
  Recommended:
    cos_graph_context(\"$FILE_PATH\", depth=1)   # or
    cos_graph_references(<symbol_uid>)
  Cheaper: ~300 tokens vs ~5K tokens for blind Read of neighbours.
  See: docs/engineering/graph-hallucination-cures.md"

if [[ "$MODE" == "strict" ]]; then
  printf '%s\n' "$MSG" >&2
  cos_log_hook enforce-graph-first-read block || true
  exit 2
fi
printf 'warning: %s\n' "$MSG" >&2
cos_log_hook enforce-graph-first-read warn || true
exit 0
