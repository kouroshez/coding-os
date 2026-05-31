#!/usr/bin/env bash
# SessionStart hook — prime agent with required-skill card per active stack.
#
# Purpose: At fresh-startup, emit a compact additionalContext card
# listing the skills that PreToolUse Write/Edit (enforce-skill.sh) will
# BLOCK without. Closes the gap where the agent only discovers required
# skills reactively after the first block. Reads SSOT:
#   $COS_STATE_DIR/installed-manifest.json::templates   → active stacks
#   src/templates/<stack>/stack.yaml                    → primary_skill + skill_enforcement
#
# SessionStart::startup fires once per session — no debounce needed.
# Always exits 0.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook session-skill-primer fire

# Resolve physical hooks dir so the helper path works even when
# .claude/hooks/<script>.sh is a symlink into src/core/hooks/.
_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
  _dir="$(cd -P "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ "$_src" != /* ]] && _src="${_dir}/${_src}"
done
HSRC="$(cd -P "$(dirname "$_src")" && pwd)"
unset _src _dir

HELPER="${HSRC}/_helpers/skill_primer.py"
if [[ ! -f "$HELPER" ]]; then
  exit 0
fi

CONTEXT=$(python3 "$HELPER" 2>/dev/null || true)
if [[ -z "$CONTEXT" ]]; then
  exit 0
fi

printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"SessionStart\",\"additionalContext\":$(printf '%s' "$CONTEXT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}"

exit 0
