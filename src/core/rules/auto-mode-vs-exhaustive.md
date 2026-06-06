# Auto-Mode vs Exhaustive Intent (Always Active)

> **Rule:** Auto mode means autonomous execution to **completeness**, not autonomous **declaration** of done. When the active prompt triggers exhaustive intent (intent.json::exhaustive=true), the auto-mode harness does NOT relax the evidence contract — it intensifies it.

## Why this rule exists

Auto mode is designed to keep the agent moving without per-step
permission prompts. It naturally rewards two behaviors:

1. **Make decisions** instead of asking.
2. **Stop when the work feels done** so the user sees a result.

Both are correct for ordinary tasks. Both are dangerous for tasks
where the user said `all` / `every` / `completely` / `until done`. In
those tasks the user has explicitly bought *coverage*, not
*judgement-call*. Auto mode without explicit handling of this
tension would let the agent declare done while the audit has unchecked
rows — exactly the failure mode the intent-enforcement layer (G0–G14)
exists to prevent.

## The tension resolution

When BOTH of the following hold:

- the harness is in auto mode (no per-step user confirmation), AND
- `.coding-os/<agent>/.intent.json::exhaustive == true`

the agent's effective contract is:

| Auto-mode default | Override under exhaustive intent |
|---|---|
| Execute reasonable assumptions | Same |
| Make decisions without asking | Same |
| Declare done when the work feels complete | **REPLACED:** declare done ONLY when ExhaustiveEvidence.counts_after is all zero AND reviewer_check=pass AND every audit-table row is Verified=yes |
| Minimize interruptions | Same |
| Prefer action over planning | Same |

Auto mode does NOT grant the right to short-circuit the guardian, the
audit artifact, the reviewer subagent, or the EvidenceBundle. Those
gates exist because the *user* bought coverage, and auto mode is
permission to keep working — not permission to redefine what was
bought.

## How the gates enforce this in practice

Even if the agent forgets this rule, the system enforces it
mechanically:

| Gate | Layer | What it does under auto-mode + exhaustive intent |
|---|---|---|
| `intent-primer` (G0) | SessionStart | Re-primes the vocabulary card every session — agent enters every turn already aware of the contract |
| `detect-exhaustive-intent` (G1) | UserPromptSubmit | Writes intent.json with predicates the agent must satisfy |
| `enforce-audit-artifact` (G12) | PreToolUse Edit/Write | Blocks edits when no audit-*.md exists with status:in_progress |
| `verify-completion-claim` (G4) | Stop | Blocks the Stop signal until predicates evaluate clean — auto mode cannot bypass |
| `prevent-premature-done` (G5) | Stop | Per-session injects "list 3 categories you excluded" — silent exclusions get surfaced |
| `enforce-count-grounding` (G7) | PreToolUse Edit/Write | Nudges grep-before/grep-after discipline |
| `enforce-subagent-delegation` (G8) | PreToolUse Edit/Write | Nudges delegation for ≥5-category audits |
| `cos_task_move` reviewer hint (G6) | MCP return value | When transitioning to complete, hint forces auto-reviewer spawn |
| `cos cognition trace-replay --audit-mode` (G14) | Retrospective | CI catches premature done across sessions |

The agent SHOULD remember the rule (it's why this doc exists). The
SYSTEM enforces the rule regardless.

## What auto mode does NOT change

- The exhaustive vocabulary is still authoritative — `all` still means *every one*.
- The predicates from intent-vocabulary.md are still the contract.
- The audit artifact is still mandatory.
- The reviewer subagent is still mandatory before "done".

## Recovery if the gate fires under auto mode

If the Stop guardian returns `decision: block` mid-auto-mode, the
agent receives the gap list as additional context and should:

1. Re-open the audit file, identify the unchecked rows.
2. Continue the per-category sweep loop (grep → fix → re-grep).
3. Update the audit file's Resume Marker before the next Stop.
4. Submit the updated ExhaustiveEvidence via
   `cos_supervise_record_output(formula_id="exhaustive_evidence")`.
5. Try Stop again — guardian re-evaluates; if clean, agent stops.

This loop is the entire point of the intent-enforcement layer. Auto
mode helps the loop run; it does not skip the loop.

## See also

- [docs/engineering/intent-vocabulary.md](../../docs/engineering/intent-vocabulary.md) — the predicate spec
- [docs/_meta/audit-checklist-template.md](../../docs/_meta/audit-checklist-template.md) — the artifact template
- [docs/_meta/reviewer-subagent-prompt.md](../../docs/_meta/reviewer-subagent-prompt.md) — the reviewer template
- [src/core/thinking_os/completion_guardian.py](../thinking_os/completion_guardian.py) — the live gate
- [src/core/rules/test-discipline.md § Per-task-class verification matrix](test-discipline.md#per-task-class-verification-matrix-task-004-g9) — the matrix
