#!/usr/bin/env bash
# Phase L.9 — PostToolUse: Rule 15 — tasks are pointers, not specs.
# Warns task bodies > 1.5k tokens; blocks > 3k tokens.
# Token estimate: word_count * 1.3.

set -eu
source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

cos_log_hook "lint-task" "entry" 2>/dev/null || true

payload="$(cos_read_stdin_bounded 5)"
file_path="$(echo "$payload" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))
except Exception:
    print("")
' 2>/dev/null || echo "")"

if [[ "$file_path" != *"docs/tasks/"*.md ]] || [[ ! -f "$file_path" ]]; then
    exit 0
fi

# Estimate tokens = words × 1.3
word_count=$(wc -w < "$file_path" 2>/dev/null || echo 0)
tokens=$(( word_count * 13 / 10 ))

if (( tokens >= 3000 )); then
    echo "ERROR lint-task: $file_path is ~${tokens} tokens (cap 3000)." >&2
    echo "  Rule 15: tasks are pointers, not specs. Link to docs; don't inline." >&2
    exit 2
elif (( tokens >= 1500 )); then
    echo "WARN lint-task: $file_path is ~${tokens} tokens (soft limit 1500)." >&2
    echo "  Consider moving content to a doc + linking (Rule 15)." >&2
fi

cos_log_hook "lint-task" "ok tokens=$tokens" 2>/dev/null || true
exit 0
