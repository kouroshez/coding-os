#!/usr/bin/env bash
# PostToolUse Write|Edit hook: warn when docs grow beyond layer-specific budgets.
# Soft limits — agent must judge whether to split or compress. No blocking.
#
# Budgets (lines, derived from header `layer:`):
#   index      ≤ 200
#   playbook   ≤ 500
#   spec       ≤ 800
#   policy     ≤ 400
#   reference  ≤ 600
#   adr        ≤ 300
#   task       ≤ 250  (tighter than lint-task soft limit; both fire OK)
# Files without a recognised layer header are skipped (not all md is governed).

set -eu
source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook "check-doc-size" "entry" 2>/dev/null || true

payload="$(cos_read_stdin_bounded 5)"
file_path="$(echo "$payload" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))
except Exception:
    print("")
' 2>/dev/null || echo "")"

# Only check md files inside docs/
case "$file_path" in
    */docs/*.md) : ;;
    *) exit 0 ;;
esac

[[ -f "$file_path" ]] || exit 0

first_line="$(head -1 "$file_path" 2>/dev/null || echo "")"
layer="$(echo "$first_line" | grep -oE 'layer:[a-z]+' | head -1 | cut -d: -f2)"
[[ -n "$layer" ]] || exit 0

case "$layer" in
    index)     budget=200 ;;
    playbook)  budget=500 ;;
    spec)      budget=800 ;;
    policy)    budget=400 ;;
    reference) budget=600 ;;
    adr)       budget=300 ;;
    task)      budget=250 ;;
    *) exit 0 ;;
esac

lines=$(wc -l < "$file_path" 2>/dev/null || echo 0)
if (( lines > budget )); then
    rel="${file_path#"$(pwd)/"}"
    echo "WARN check-doc-size: $rel is ${lines} lines (layer:$layer budget ${budget})." >&2
    echo "  Consider splitting into a sub-doc or compressing prose." >&2
fi

cos_log_hook "check-doc-size" "ok lines=$lines layer=$layer" 2>/dev/null || true
exit 0
