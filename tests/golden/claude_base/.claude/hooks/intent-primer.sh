#!/usr/bin/env bash
# SessionStart hook — prime agent with intent-interpretation vocabulary.
#
# Purpose: Inject a compact (≤300 token) card at every session boundary
# (startup, compact, resume) so the agent enters every session already
# aware of how to read natural-language exhaustive intent — "all" /
# "every" / "completely" / "down to the last one" — and what evidence is required when
# such intent is detected.
#
# Three-layer architecture (this is layer 1):
#   SessionStart::intent-primer  — always-on prime card (this file)
#   UserPromptSubmit::detect-exhaustive-intent  — per-prompt refinement
#   Stop::verify-completion-claim  — evidence verification
#
# Full vocabulary + predicate contract: docs/engineering/intent-vocabulary.md.
# Always exits 0 (informational, never blocks).
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook intent-primer fire

# Clear stale intent.json + per-session debounce markers on every
# SessionStart.  Intent is per-prompt, not per-session — without this,
# a previous session's exhaustive=true leaks into the new session and
# the Stop guardian fires on a stale predicate set the agent cannot
# satisfy (the EvidenceBundle is keyed on the new session id which
# never received the prior predicates).
#
# Detected during self-review when the guardian blocked Stop
# after session rotation with "no EvidenceBundle for predicates
# ['coverage_100']" — the predicates were from a prompt the agent
# never saw in the new session.
# Clear at BOTH panel and agent scope: the markers are now
# panel-first, but a pre-migration agent-dir copy may still linger.
for _D in "${COS_PANEL_DIR:-}" "${COS_AGENT_DIR:-}"; do
  [[ -n "$_D" ]] || continue
  rm -f "${_D}/.intent.json" 2>/dev/null || true
  rm -f "${_D}/.premature-done-nudged" 2>/dev/null || true
  rm -f "${_D}/.count-grounding-nudged" 2>/dev/null || true
  rm -f "${_D}/.subagent-delegation-nudged" 2>/dev/null || true
done

# The card text lives next to this script — keeps the bash heredoc out
# of `CONTEXT=$(cat <<HEREDOC ... HEREDOC)`, which deadlocks bash 5.3.9
# on macOS (CLAUDE.md Rule 8). Each deadlocked invocation orphaned an
# `intent-primer.sh` worker, and Claude Code's 60s subprocess-init
# timeout fired after enough orphans piled up — visible as
# `Subprocess initialization did not complete within 60000ms` and
# every MCP server (coding-os, gmail, drive, …) cleanly closing
# after 60s.
# Follow the symlink that consumer projects (or this repo's own
# .claude/hooks/) install — without `readlink -f` the card file would
# resolve next to the symlink (.claude/hooks/) and never exist there.
_HOOK_SRC="${BASH_SOURCE[0]:-$0}"
if command -v readlink >/dev/null 2>&1 && readlink -f "$_HOOK_SRC" >/dev/null 2>&1; then
  _HOOK_REAL="$(readlink -f "$_HOOK_SRC")"
else
  # macOS BSD readlink lacks -f; emulate with Python.
  _HOOK_REAL="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$_HOOK_SRC")"
fi
CARD_FILE="$(dirname "$_HOOK_REAL")/_intent_primer_card.txt"

if [[ ! -f "$CARD_FILE" ]]; then
  # Defensive: never abort the agent on a missing primer card.
  printf '%s' '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":""}}'
  exit 0
fi

# Read the card file and JSON-encode it. The `--card` arg keeps the file
# path out of stdin so this hook can stay stdin-clean for the agent
# runtime (which may still send the SessionStart JSON we choose to ignore).
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
