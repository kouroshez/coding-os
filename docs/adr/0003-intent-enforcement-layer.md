# ADR-0003: Intent-enforcement layer for exhaustive vocabulary

- **Status:** Accepted (2026-05-12)
- **Deciders:** Kourosh Ebrahimzadeh
- **Context tags:** workflow, completion-bias, agent-discipline

## Context

A recurring failure pattern in AI coding agents (across Claude
Code, Codex, Cursor) is **premature completion** under exhaustive
instructions. The user says "" (all) or "until done" or
"comprehensive", expecting full coverage. The agent does ~60% of
the work, picks the most visible categories, declares "done", and
files the rest under unstated assumptions.

The agent is **not** lying — it genuinely believes it finished, by
applying a relaxed definition of completion. The cost falls on the
user who later discovers gaps that were the very point of the
exhaustive instruction.

The straightforward fix — "just be more thorough" — does not work,
because the agent has no persistent memory of what "thorough" meant
in this specific user's vocabulary. Each session resets.

## Decision

Build an enforcement layer (G0–G14) that:

- **Detects exhaustive intent** at prompt time (G1, regex over
  bilingual FA + EN vocabulary in
  `docs/engineering/intent-vocabulary.md`).
- **Materializes the contract** as `.coding-os/<agent>/.intent.json`
  with predicates the agent must satisfy (G3).
- **Requires an audit artifact** at `docs/tasks/audits/audit-<slug>.md`
  before code edits can proceed (G12, PreToolUse Write/Edit hook
  blocks).
- **Refuses the Stop signal** when predicates aren't satisfied (G4,
  Stop hook). The agent gets a structured gap-list back as context.
- **Forces a reviewer subagent** before "done" claims on
  ≥ 5-category audits (G6/G8, hint on `cos_task_move` return value).
- **Snapshots the result** as an `ExhaustiveEvidence` bundle (G3)
  recorded via `cos_supervise_record_output`.
- **Replays in CI** (`cos cognition trace-replay --audit-mode`, G14)
  so premature-done in one session surfaces in later trace audits.

The layer is **opt-in by user vocabulary** — non-exhaustive prompts
go through the existing happy path with zero new gates. Auto-mode
does not relax the contract (see
`src/core/rules/auto-mode-vs-exhaustive.md`).

## Consequences

**Positive:**

- Exhaustive instructions become enforceable rather than
  best-effort. The system catches the agent when it tries to
  short-circuit.
- Audit artifacts give the user a single file to scan instead of
  having to reconstruct what the agent did.
- Cross-session learning loop (G11): completion-gap observations
  feed the learning layer so future similar prompts trigger the
  audit path automatically.
- Bilingual vocabulary (FA + EN) handles the project's primary
  user pair without requiring translation.

**Negative:**

- 14 new gates is a lot of surface area to maintain. Each gate has
  a test, a doc anchor, and an integration path.
- Some legitimate quick edits get nudged into audit mode if the
  prompt happens to contain a trigger word. The reviewer-subagent
  delegation hint can feel heavy for a one-line fix.
- The intent vocabulary is biased toward the project's primary
  language pair (FA + EN); adding more languages is per-language
  vocabulary work.

**Mitigations:**

- The trigger detector requires BOTH an exhaustive word AND a
  scope verb (find/fix/audit/migrate/rename/verify/sweep), which
  cuts false positives.
- An escape hatch exists: explicit "skip audit" in the prompt
  bypasses the gate (logged).
- Per-task-class verification matrix in
  `src/core/rules/test-discipline.md` documents the gate
  obligations so the agent can plan around them.

## Alternatives considered

- **Trust the agent to be thorough.** Rejected — empirically
  false; the failure rate without enforcement was high enough to
  motivate the layer.
- **Single Stop-only gate.** Rejected — by the time Stop fires,
  the work is wrong-shape; the audit-artifact-at-edit-time gate
  catches it earlier.
- **Heavier UI (per-step confirmation).** Rejected — interrupts
  flow for non-exhaustive tasks. The layered approach (detect →
  contract → enforce → audit → replay) keeps non-exhaustive paths
  untouched.
