#!/usr/bin/env bash
# PostToolUse hook: remind the mother-project to eat its own DNA.
#
# coding-os is a meta-project. When core/** or adapters/** change, the
# repo's own .claude/ and .codex/ are stale until `make dogfood-full`
# re-runs the install scripts. This hook detects DNA-layer edits and
# reminds once per debouncing window.
#
# Only fires inside the meta-project itself — consumer projects don't
# have the source tree, so the reminder would be noise there. We detect
# meta-project by the presence of templates/_base/ + adapters/claude/
# + adapters/codex/ in the same root as the edit.
#
# Non-blocking, debounced (one reminder per 10 minutes) to avoid spam.
set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
[[ -z "$FILE_PATH" ]] && exit 0

case "$FILE_PATH" in
  */core/hooks/*|*/core/rules/*|*/core/skills/*|*/core/thinking-os/*|*/adapters/*)
    ;;
  *)
    exit 0
    ;;
esac

# Locate project root + verify it's the meta-project (not a consumer).
DIR=$(dirname "$FILE_PATH")
PROJECT_ROOT=""
while [[ "$DIR" != "/" && "$DIR" != "." ]]; do
  if [[ -d "${DIR}/templates/_base" && -d "${DIR}/adapters/claude" && -d "${DIR}/adapters/codex" ]]; then
    PROJECT_ROOT="$DIR"
    break
  fi
  DIR=$(dirname "$DIR")
done
[[ -z "$PROJECT_ROOT" ]] && exit 0

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
cos_log_hook remind-dogfood fire "path=${FILE_PATH}"

MARKER="${PROJECT_ROOT}/.coding-os/.dogfood-reminded"
NOW=$(date +%s)
DEBOUNCE_SEC=600

if [[ -f "$MARKER" ]]; then
  LAST=$(cat "$MARKER" 2>/dev/null || echo 0)
  if [[ $((NOW - LAST)) -lt $DEBOUNCE_SEC ]]; then
    exit 0
  fi
fi

echo "$NOW" > "$MARKER" 2>/dev/null || true
cos_log_hook remind-dogfood reminded ""

cat >&2 <<'MSG'
🧬 Meta-project reminder — you edited DNA (core/** or adapters/**).

   The repo's own .claude/ and .codex/ are now out of sync with core/.
   Run: make dogfood-full
   to re-install both adapters with the latest DNA.

   (This reminder debounces for 10 minutes. `cos hooks-log` shows when it fires.)
MSG

exit 0
