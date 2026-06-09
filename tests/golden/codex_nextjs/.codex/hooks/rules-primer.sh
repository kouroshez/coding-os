#!/usr/bin/env bash
# SessionStart hook — prime the agent with the workflow-integrity rules card.
#
# Purpose: Inject a compact (~200 token) card at every session boundary
# (startup, compact, resume) so the agent enters turn-1 already knowing the
# Rule 25 contract — task/audit status changes go through cos_task_move /
# cos_supervise_record_output (never a hand-Edit), task lookup via
# cos task-show / cos_task_search (never ls/grep), gate via cos_classify_prompt,
# and that cos_* tools are deferred (ToolSearch before first use).
#
# Prime-card pattern: card text
# lives in a sibling .txt to keep the bash heredoc out of $(...) (Rule 8
# deadlock). Always exits 0 (informational, never blocks).
#
# Full contract: docs/governance/critical-rules.md § Rule 25.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook rules-primer fire

# Resolve the physical hooks dir through the .claude/hooks symlink so the
# sibling card file is found (BSD readlink lacks -f → python fallback).
_HOOK_SRC="${BASH_SOURCE[0]:-$0}"
if command -v readlink >/dev/null 2>&1 && readlink -f "$_HOOK_SRC" >/dev/null 2>&1; then
  _HOOK_REAL="$(readlink -f "$_HOOK_SRC")"
else
  _HOOK_REAL="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$_HOOK_SRC")"
fi
CARD_FILE="$(dirname "$_HOOK_REAL")/_rules_primer_card.txt"

if [[ ! -f "$CARD_FILE" ]]; then
  printf '%s' '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":""}}'
  exit 0
fi

python3 -c '
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    card = f.read()
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": card,
    }
}))
' "$CARD_FILE"

exit 0
