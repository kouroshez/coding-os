#!/usr/bin/env bash
# enforce-graph-context.sh
# Warn (default) or block (strict) when an Edit targets a file listed
# under .coding-os/rag-config.yaml::graph.enforce_context_on without a
# matching .graph-context-<uid> marker in $COS_AGENT_DIR.

set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

# Note: no unconditional `enter` log. Skip-reason logs below (`disabled`,
# `no-file`, `no-config`, `skip`, `ok`, `warn`, `block`) already give
# full observability without polluting the hook stream with `enter` rows
# for every Write/Edit.

# Default-on at "warn" so agents discover the graph_os layer instead
# of writing blind to load-bearing files. Opt-out: COS_ENFORCE_GRAPH_CONTEXT=off
# Opt-in stricter mode: COS_ENFORCE_GRAPH_CONTEXT=strict (block on miss).
MODE="${COS_ENFORCE_GRAPH_CONTEXT:-1}"
if [[ "$MODE" == "off" || "$MODE" == "0" ]]; then
  cos_log_hook enforce-graph-context disabled || true
  exit 0
fi

# Accept stdin JSON from Claude / Codex dispatchers. jq (the house pattern)
# is ~30ms cheaper than a python3 spawn — material on the Write|Edit hot path.
FILE_PATH="$(cos_read_stdin_bounded 2 | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)"

if [[ -z "$FILE_PATH" ]]; then
  cos_log_hook enforce-graph-context no-file || true
  exit 0
fi

CONFIG="${COS_STATE_DIR:-.coding-os}/rag-config.yaml"
[[ -f "$CONFIG" ]] || CONFIG="$(pwd)/.coding-os/rag-config.yaml"
if [[ ! -f "$CONFIG" ]]; then
  cos_log_hook enforce-graph-context no-config || true
  exit 0
fi

# Ask Python to decide whether FILE_PATH matches the configured globs.
# bash 5.3.9 deadlocks `$(python3 - <<HEREDOC)`; extracted to helper.
_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
  _dir="$(cd -P "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ "$_src" != /* ]] && _src="$_dir/$_src"
done
HSRC="$(cd -P "$(dirname "$_src")" && pwd)"
unset _src _dir
HELPER="${HSRC}/_helpers/graph_context_match.py"
if [[ -f "$HELPER" ]]; then
  MATCHED="$(python3 "$HELPER" "$CONFIG" "$FILE_PATH" 2>/dev/null || echo no)"
else
  MATCHED="no"
fi
if [[ "$MATCHED" != "yes" ]]; then
  cos_log_hook enforce-graph-context skip || true
  exit 0
fi

MARKER="${COS_AGENT_DIR:-.coding-os/claude}/.graph-context-$(printf '%s' "$FILE_PATH" | sha1sum | awk '{print $1}')"
if [[ -f "$MARKER" ]]; then
  cos_log_hook enforce-graph-context ok || true
  exit 0
fi

MSG="graph-context missing for $FILE_PATH.
  Rule: call cos_graph_context before editing a load-bearing file.
  Record the marker after reviewing:
    bash ${BASH_SOURCE[0]%/*}/write-state.sh \"${MARKER#$(pwd)/}\" \"consulted\""
if [[ "$MODE" == "strict" ]]; then
  printf '%s\n' "$MSG" >&2
  cos_log_hook enforce-graph-context block || true
  exit 2
fi
printf 'warning: %s\n' "$MSG" >&2
cos_log_hook enforce-graph-context warn || true
exit 0
