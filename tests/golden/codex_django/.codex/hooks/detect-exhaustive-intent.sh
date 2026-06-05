#!/usr/bin/env bash
# UserPromptSubmit hook — detect exhaustive-scope intent in user prompt.
#
# Layer 2 of the 3-layer intent architecture (Layer 1 = SessionStart
# intent-primer card; Layer 3 = Stop verify-completion-claim guardian).
#
# Reads the prompt, delegates parsing to _helpers/extract_intent.py
# (which mirrors docs/engineering/intent-vocabulary.md), writes the
# parsed intent to $COS_AGENT_DIR/.intent.json, and when exhaustive
# intent is detected, injects a one-line additionalContext block so
# the agent enters evidence-required mode for this prompt.
#
# Downstream consumers read .intent.json (not chat) — enforce-audit-
# artifact.sh, enforce-count-grounding.sh, enforce-subagent-delegation.sh,
# completion_guardian.py, auto-reviewer spawn on cos task-done.
#
# Always exits 0. Silent for non-exhaustive prompts.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_require_or_skip python3 detect-exhaustive-intent

INPUT="$(cos_read_stdin_bounded 2)"
if [[ -z "$INPUT" ]]; then
  exit 0
fi

PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty' 2>/dev/null || echo "")
LEN=${#PROMPT}

HELPER="$(dirname "$0")/_helpers/extract_intent.py"
if [[ ! -f "$HELPER" ]]; then
  cos_log_hook detect-exhaustive-intent skip "reason=helper_missing"
  exit 0
fi

# Always invoke helper — even for short / empty prompts — so intent.json
# is OVERWRITTEN every UserPromptSubmit.  Without this, stale
# exhaustive=true from an earlier prompt persists into later turns where
# the user moved on to a non-exhaustive ask, and the Stop guardian
# fires on ghost predicates the current bundle cannot satisfy.
INTENT_ERR=$(mktemp)
INTENT_RC=0
INTENT_JSON=$(printf '%s' "$INPUT" | python3 "$HELPER" 2>"$INTENT_ERR") || INTENT_RC=$?
INTENT_STDERR=$(cat "$INTENT_ERR" 2>/dev/null || true); rm -f "$INTENT_ERR"
if [[ "$INTENT_RC" -ne 0 || -z "$INTENT_JSON" ]]; then
  # Helper crash: surface LOUD to the eye (was a silent skip — we never knew
  # exhaustive-intent detection had broken). Default stays open (no enforcement
  # this turn) for availability, but it is no longer silent.
  cos_say error hook.detect_exhaustive_intent "intent helper failed (rc=${INTENT_RC}) — exhaustive detection skipped this turn" detail="${INTENT_STDERR:0:200}" 2>/dev/null || true
  cos_log_hook detect-exhaustive-intent skip "reason=helper_failed rc=${INTENT_RC}" || true
  exit 0
fi

if [[ "$LEN" -lt 5 ]]; then
  cos_log_hook detect-exhaustive-intent ok "short_prompt len=${LEN} intent_reset"
  exit 0
fi

EXHAUSTIVE=$(printf '%s' "$INTENT_JSON" | jq -r '.exhaustive // false' 2>/dev/null || echo "false")

if [[ "$EXHAUSTIVE" != "true" ]]; then
  cos_log_hook detect-exhaustive-intent ok "exhaustive=false len=${LEN}"
  exit 0
fi

MATCHED=$(printf '%s' "$INTENT_JSON" | jq -r '.matched_exhaustive | join(", ")' 2>/dev/null || echo "")
SCOPE=$(printf '%s' "$INTENT_JSON" | jq -r '.matched_scope | join(", ")' 2>/dev/null || echo "")
PREDICATES=$(printf '%s' "$INTENT_JSON" | jq -r '.predicates | join(", ")' 2>/dev/null || echo "")

cos_log_hook detect-exhaustive-intent fire "exhaustive=true matched=[${MATCHED}] scope=[${SCOPE}]"

CONTEXT="[Intent: exhaustive detected] verbs=[${MATCHED}] · scope=[${SCOPE}] · predicates=[${PREDICATES}]. Evidence-required mode active: produce docs/tasks/audits/audit-<slug>.md table, report counts before/after fix per category, satisfy EvidenceBundle (counts_after=0) before any 'done' claim. Completion guardian (Stop) and auto-reviewer (task-done) will reject otherwise. Full predicate spec: docs/engineering/intent-vocabulary.md."

printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":$(printf '%s' "$CONTEXT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}"

exit 0
