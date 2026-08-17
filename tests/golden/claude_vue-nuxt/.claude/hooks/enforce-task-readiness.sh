#!/usr/bin/env bash
# enforce-task-readiness.sh (PreToolUse) — a card must declare its pull-state.
#
# BLOCKs a create that would land an icebox card carrying none of `ready`
# (queue it), `parked` (deliberate backlog), or `keep` (reference only). Such a
# card is invisible to cos_task_pick / cos_task_claim_next, so nothing will ever
# pull it — and every earlier countermeasure was a report that arrived after the
# agent had already told the operator the work was filed. Resolves DC-2.
#
# Covers both surfaces: the MCP tool and `cos task-create` via Bash.
#
# Fail-open on infrastructure failure, deliberately: warn-abandoned-task.sh
# still catches create-then-park at Stop, so a broken helper degrades to the
# previous behaviour instead of blocking all task creation. A non-zero helper rc
# is logged so the degradation is visible in `cos hooks-log`, never silent.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(printf '%s' "$INPUT" | cos_json_field tool_name 2>/dev/null || true)

# Fast path: this hook rides the Bash matcher to cover the CLI surface, so it
# must cost nothing on the overwhelming majority of Bash calls.
case "$TOOL" in
  mcp__coding-os__cos_task_create) ;;
  Bash)
    printf '%s' "$INPUT" | grep -q "task-create" || exit 0
    ;;
  *) exit 0 ;;
esac

_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
  _dir="$(cd -P "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ "$_src" != /* ]] && _src="$_dir/$_src"
done
HELPER="$(cd -P "$(dirname "$_src")" && pwd)/_helpers/task_readiness_check.py"
[[ -f "$HELPER" ]] || exit 0

set +e
VERDICT_JSON=$(printf '%s' "$INPUT" | python3 "$HELPER" 2>/dev/null)
HELPER_RC=$?
set -e
if [[ "$HELPER_RC" -ne 0 || -z "$VERDICT_JSON" ]]; then
  cos_log_hook enforce-task-readiness warn "helper rc=${HELPER_RC} — readiness unchecked" || true
  exit 0
fi

VERDICT=$(printf '%s' "$VERDICT_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("verdict",""))' 2>/dev/null || true)
if [[ "$VERDICT" == "block" ]]; then
  # Print on stdout and redirect to stderr here: writing to stderr inside the
  # helper and then adding `2>/dev/null` to the call discards the remediation
  # message, which is the one thing a block must always carry.
  MESSAGE=$(printf '%s' "$VERDICT_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("message",""))' || true)
  printf '%s\n' "$MESSAGE" >&2
  cos_log_hook enforce-task-readiness block "rule=no-pull-state tool=${TOOL}" || true
  exit 2
fi

exit 0
