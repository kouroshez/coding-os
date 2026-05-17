#!/usr/bin/env bash
# SessionStart hook — prime agent with intent-interpretation vocabulary.
#
# Purpose: Inject a compact (≤300 token) card at every session boundary
# (startup, compact, resume) so the agent enters every session already
# aware of how to read natural-language exhaustive intent — "همه" / "all"
# / "completely" / "تا دونه آخر" — and what evidence is required when
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

CONTEXT=$(cat <<'CARD'
[Intent Layer] Agent reads natural-language scope vocabulary at every prompt.

Exhaustive markers trigger evidence-required mode when paired with a scope verb (find · fix · audit · migrate · rename · verify · sweep).

FA exhaustive: همه · همگی · کامل · کاملا · تک به تک · تا اخر · تا دونه آخر · هر چی · همه جا · هیچی نپره · بدون استثنا · تمام · صد در صد

EN exhaustive: all · every · everywhere · completely · comprehensive · exhaustive · thorough · until done · none missed · 100% · down to the last one · each and every

When triggered, the agent MUST:
1. Produce docs/tasks/audits/audit-<slug>.md with mandatory category table.
2. Report grep-count BEFORE fix per category.
3. Iterate fix → re-grep until count AFTER = 0.
4. Submit EvidenceBundle (counts_before, counts_after, categories_covered, gaps_remaining) via cos_supervise_record_output.
5. Pass independent reviewer subagent re-grep before "done".

The completion guardian (Stop) and auto-reviewer (task-done) will reject any "done" claim that does not satisfy these. This is non-negotiable for tasks where the user used exhaustive vocabulary — that vocabulary IS the contract.

Full predicate spec: docs/engineering/intent-vocabulary.md
CARD
)

# Emit as SessionStart additionalContext so the card lands in agent context
# (plain stdout would only surface as a status line).
printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"SessionStart\",\"additionalContext\":$(printf '%s' "$CONTEXT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}"

exit 0
