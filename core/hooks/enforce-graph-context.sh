#!/usr/bin/env bash
# enforce-graph-context.sh (Phase I.14)
# Warn (default) or block (strict) when an Edit targets a file listed
# under .coding-os/rag-config.yaml::graph.enforce_context_on without a
# matching .graph-context-<uid> marker in $COS_AGENT_DIR.

set -eu

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
cos_log_hook enforce-graph-context enter || true

MODE="${COS_ENFORCE_GRAPH_CONTEXT:-}"   # unset = disabled; 1 = warn; strict = block
if [[ -z "$MODE" ]]; then
  cos_log_hook enforce-graph-context disabled || true
  exit 0
fi

# Accept stdin JSON from Claude / Codex dispatchers.
PAYLOAD="$(cat 2>/dev/null || true)"
FILE_PATH="$(printf '%s' "$PAYLOAD" | python3 -c '
import sys, json
try:
    data = json.loads(sys.stdin.read() or "{}")
except Exception:
    print("")
    raise SystemExit(0)
print(data.get("tool_input", {}).get("file_path", ""))
' 2>/dev/null || true)"

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
MATCHED="$(
python3 - <<PY 2>/dev/null
import fnmatch, yaml, sys
with open("${CONFIG}", "r", encoding="utf-8") as fh:
    data = yaml.safe_load(fh) or {}
patterns = (((data.get("graph") or {}).get("enforce_context_on")) or [])
fp = "${FILE_PATH}"
for pat in patterns:
    if fnmatch.fnmatchcase(fp, pat):
        print("yes")
        break
else:
    print("no")
PY
)"
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
