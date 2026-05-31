#!/usr/bin/env bash
# Stop hook — refuse "done" when exhaustive intent has unmet evidence.
#
# Layer 3 of the 3-layer intent architecture (Layer 1 = SessionStart
# intent-primer; Layer 2 = UserPromptSubmit detect-exhaustive-intent).
#
# Delegates to src/core/thinking_os/completion_guardian.py which:
#   1. Reads $COS_AGENT_DIR/.intent.json — if exhaustive=false, pass.
#   2. Scans docs/tasks/audits/audit-*.md for status:in_progress files
#      and counts unchecked rows (`| no |` in the Verified column).
#   3. Loads the session's EvidenceBundle and runs
#      validate_exhaustive_evidence over the active predicates.
#   4. Aggregates all gaps; status="fail" iff exhaustive ∧ gaps non-empty.
#
# When status=fail: emits Claude Code stop-decision JSON with
# decision:"block" and reason listing the gaps so the agent continues
# the audit loop rather than declaring done prematurely.
#
# Always exits 0 — the block signal is in the JSON envelope, not the
# exit code, so failures inside the guardian never silently terminate
# the agent loop. Fail-open by design.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_require_or_skip python3 verify-completion-claim

# Resolve physical hooks dir (symlinks in consumer projects).
_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
  _dir="$(cd -P "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ "$_src" != /* ]] && _src="${_dir}/${_src}"
done
HOOKS_PHYS="$(cd -P "$(dirname "$_src")" && pwd)"
unset _src _dir

# completion_guardian.py lives next to cognition_schemas, two dirs up
# from src/core/hooks/_helpers/. The hook itself is in src/core/hooks/,
# so the guardian path is <repo>/src/core/thinking_os/completion_guardian.py.
GUARDIAN="${HOOKS_PHYS}/../thinking_os/completion_guardian.py"
if [[ ! -f "$GUARDIAN" ]]; then
  cos_log_hook verify-completion-claim skip "reason=guardian_missing path=${GUARDIAN}"
  exit 0
fi

INPUT="$(cos_read_stdin_bounded 2)"

RESULT_JSON=$(printf '%s' "$INPUT" | python3 "$GUARDIAN" 2>/dev/null || echo '')
if [[ -z "$RESULT_JSON" ]]; then
  cos_log_hook verify-completion-claim skip "reason=guardian_empty"
  exit 0
fi

STATUS=$(printf '%s' "$RESULT_JSON" | jq -r '.status // "pass"' 2>/dev/null || echo "pass")
EXHAUSTIVE=$(printf '%s' "$RESULT_JSON" | jq -r '.intent_exhaustive // false' 2>/dev/null || echo "false")
GAPS=$(printf '%s' "$RESULT_JSON" | jq -r '.gaps | join("; ")' 2>/dev/null || echo "")

if [[ "$STATUS" != "fail" ]]; then
  cos_log_hook verify-completion-claim ok "exhaustive=${EXHAUSTIVE}"
  exit 0
fi

cos_log_hook verify-completion-claim block "gaps=${GAPS}"

REASON="GAPS detected — cannot stop yet. ${GAPS}. Re-open the active audit artifact, fix the unchecked rows (counts_after must reach 0 and Verified must flip to yes per row), and only after every row is verified may you submit ExhaustiveEvidence via cos_supervise_record_output (formula_id='exhaustive_evidence'). The auto-reviewer subagent (G6) provides the final stamp."

printf '%s' "{\"decision\":\"block\",\"reason\":$(printf '%s' "$REASON" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}"

exit 0
