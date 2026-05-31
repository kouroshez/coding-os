# Anti-Overengineering (Always Active)

> **Hard rule:** Solve the problem in front of you with the smallest correct change. Reuse what exists. Don't speculate. Don't duplicate.

This rule is cross-cutting — it applies to every artifact, not just code: docs, hooks, skills, templates, tests, CLI, configs. Every "should I add this?" question goes through this filter first.

Full rationale + numbered index: [docs/governance/critical-rules.md § Rule 22](../../docs/governance/critical-rules.md#rule-22--anti-overengineering).

## Why

Over-engineering shows up in every layer: a new helper for something that already exists; a config flag for a hypothetical future user; a 3-layer abstraction for a function called from one place; a re-implementation because the existing version "doesn't quite fit"; a refactor bundled with a bug fix; a new doc for a topic already covered in another doc.

Each instance feels harmless on its own. Cumulatively they:

- Grow surface area — every new abstraction is another contract to maintain.
- Hide intent — callers traverse layers to find the actual logic.
- Slow review — more diff to read, more places to break, more guesses to verify.
- Train future agents that this is the house pattern (cascade — the next agent copies the bloat).
- Increase coupling — duplicated logic drifts; one site gets fixed, the other doesn't.

In an enterprise codebase, the cost of *every line that exists* is paid forever. Cheaper to not write it.

## The five sub-rules

### 1. Reuse-First (mirrors P1 SSOT-first)

Before writing **anything** — code, doc, hook, skill, template — search:

- `cos_graph_query` / `cos_graph_context` — does a similar symbol exist?
- `cos_search` — has this pattern been solved in a past session?
- `cos_doc_search` — does a spec / playbook already cover it?
- grep / find for the literal — is the string already present?

If a sibling exists, **extend or reuse**. Never copy-paste. Never reimplement a stdlib / framework primitive (`my_chunk`, `safeJsonParse`, `slugify_v2` — almost always already exist).

### 2. No-Speculation

Build only what the current task requires. Reject:

- "We might need this later" → file a task instead.
- "In case we add X" → wait until X is real.
- Generic helpers with zero current callers → inline at the single call site.
- Configuration switches with one branch that never runs in production.
- `IFoo` interface when there is one implementation.

Documented future work goes to `docs/tasks/`, not to code.

### 3. Diff-Minimal (mirrors P4 Diff-first)

Smallest correct change. Specifically:

- Bug fix → just the bug, no surrounding cleanup ride-along.
- One-shot operation → no helper extraction.
- "I refactored while I was there" — split into a separate commit/PR.
- Three similar lines is better than a premature abstraction.

If unrelated cleanup IS needed, file it as its own task.

### 4. No-Premature-Abstraction (Rule of Three)

Don't extract an abstraction until **three** real, divergent call sites need it. Two callers? Inline. Two-and-a-half (one is conditionally similar)? Inline.

When abstraction does appear, prove it can absorb the third caller without growing parameters. If the parameter list is already getting weird at three callers, you abstracted on the wrong axis — try again.

### 5. Defer-by-Default

When the task is done, ask: **"what can I remove?"** — not "what should I add?". Sweep for:

- Unused parameters / dead imports / unreferenced functions.
- Feature flags for features that shipped (collapse) or never shipped (delete).
- Half-finished implementations (`# TODO finish later` with no task).
- Comments that restate the code.
- Re-exports of types that nothing imports.

## When refactoring / adding *is* justified

A non-trivial addition or refactor is justified when **at least one** of these is true:

- The current code is actively preventing the task (blocking edit, broken type, deadlock).
- Three call sites have converged independently — extract now.
- A documented incident / post-mortem demanded the change.
- The user explicitly asked for the refactor.

Otherwise: file a task, ship the smallest fix.

## Anti-patterns (reject in review, fix on sight)

- New file added when an existing file has the right namespace.
- New skill / hook / rule when an existing one already covers the matcher.
- A class that wraps one method that calls one external function.
- Configuration switch with one branch never exercised in production.
- Helper introduced "for testability" when the original was already testable.
- "I refactored while I was there" — bundled with a bug fix.
- Reimplementing a stdlib / framework function.
- Adding `IFoo` interface when there is one implementation.
- New doc file when an existing doc has the right scope — add a section instead.
- Two skills with overlapping globs — merge them.
- Two rules with overlapping triggers — merge them.

## Reality check — run before any non-trivial addition

| Question | Tool |
|---|---|
| Does this already exist? | `cos_graph_query`, `cos_doc_search`, grep |
| Does this need to exist *now*? | Is there a real current caller, or is this speculation? |
| Will I remove this if the next task is canceled? | If yes, don't add it now — file a task. |
| Is this someone else's already-solved problem? | stdlib, framework, existing skill / playbook. |
| Is the abstraction earned? | Three divergent call sites — not two, not "could see three coming". |
| Could three inlined lines be clearer than one helper? | Often yes. Pick clarity. |

## Enforcement

This rule is **convention** — no automated hook can reliably detect over-engineering (false-positive rate too high on numeric thresholds, abstraction counts, file additions). Enforcement is:

- Self-review against this rule before submitting a diff.
- Code review rejects diffs that fail the reality check above.
- `cos_search` records prior over-engineering incidents as observations so patterns surface across sessions.
- The `clean-code` skill enforces the **tactical** instances at the symbol level (no abbreviations, no magic numbers, no positional booleans, nesting ≤ 2) — those are this rule applied to naming and structure.

## See also

- [src/core/rules/api-contract-discipline.md](api-contract-discipline.md) — don't reinvent the producer's shape.
- [src/core/rules/test-discipline.md](test-discipline.md) — matrix command, not full sweep.
- [src/core/skills/clean-code/SKILL.md](../skills/clean-code/SKILL.md) — tactical naming / structure rules.
- [src/core/skills/simplify/SKILL.md](../skills/simplify/SKILL.md) — review-existing-code-for-reuse loop.
- [docs/governance/critical-rules.md § Rule 22](../../docs/governance/critical-rules.md#rule-22--anti-overengineering) — full rationale + index.
