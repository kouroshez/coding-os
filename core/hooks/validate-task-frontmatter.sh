#!/usr/bin/env bash
# Phase L.4 — PreToolUse: Write/Edit on docs/tasks/*.md
# Validates the Phase L lean frontmatter (id/swimlane/kind/epic/labels/
# status/priority/appetite/depends_on) before the file is written.
# Also enforces WIP caps when status transitions to in_progress/emergency,
# and rejects dependency cycles (R-L-29).
#
# Fail-soft: if board_os python module is unavailable (e.g. fresh clone
# before `uv sync`), hook warns but does NOT block — avoids bricking
# the session on toolchain drift.

set -euo pipefail
source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

cos_log_hook "validate-task-frontmatter" "entry" 2>/dev/null || true

# Read JSON payload from stdin (Claude/Codex hook input format).
payload="$(cat)"

# Only act on docs/tasks/*.md writes.
file_path="$(echo "$payload" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    p = d.get("tool_input", {}).get("file_path", "")
    print(p)
except Exception:
    print("")
' 2>/dev/null || echo "")"

if [[ -z "$file_path" ]] || [[ "$file_path" != *"docs/tasks/"*.md ]]; then
    exit 0
fi

# Skip if file doesn't exist yet (Write creating new) — we need the
# candidate content. The hook protocol passes `content` in tool_input.
# bash 5.3.9 deadlocks `python3 - <<HEREDOC`; helper file is the safe form.
_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
  _dir="$(cd -P "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ "$_src" != /* ]] && _src="$_dir/$_src"
done
HSRC="$(cd -P "$(dirname "$_src")" && pwd)"
unset _src _dir
HELPER="${HSRC}/_helpers/validate_task_frontmatter.py"
if [[ -f "$HELPER" ]]; then
  python3 "$HELPER" "$payload"
else
  exit 0
fi

exit_code=$?
cos_log_hook "validate-task-frontmatter" "$([[ $exit_code -eq 0 ]] && echo allow || echo block)" 2>/dev/null || true
exit $exit_code
