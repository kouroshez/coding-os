# Anti-Overengineering (Always Active)

> **Hard rule:** Solve the problem in front of you with the smallest correct change. Reuse what exists. Don't speculate. Don't duplicate. Cross-cutting — applies to every artifact (code, docs, hooks, skills, templates, tests, CLI, configs).

Why (cumulative cost of every line): [critical-rules.md § Rule 22](../../docs/governance/critical-rules.md#rule-22--anti-overengineering).

## The six sub-rules

**1. Reuse-First** (mirrors P1 SSOT-first) — before writing **anything**, search `cos_graph_query`/`cos_graph_context` (similar symbol?), `cos_search` (solved before?), `cos_doc_search` (spec exists?), grep/find (literal present?). Sibling exists → extend or reuse, never copy-paste, never reimplement a stdlib/framework primitive.

**2. No-Speculation** — build only what the current task requires. Reject "might need it later", "in case we add X", generic helpers with zero callers, one-branch config switches, `IFoo` with one implementation. Documented future work goes to `docs/tasks/`, not code.

**3. Diff-Minimal** (mirrors P4 Diff-first) — bug fix touches just the bug; no ride-along cleanup; one-shot operation gets no helper extraction; three similar lines beat a premature abstraction. Unrelated cleanup → its own task.

**4. No-Premature-Abstraction (Rule of Three)** — extract only when **three** real, divergent call sites need it. Two (or two-and-a-half)? Inline. If the parameter list is already weird at three callers, the abstraction axis is wrong.

**5. Defer-by-Default** — at task close ask "what can I remove?", not "what should I add?". Sweep for unused params, dead imports, unreferenced functions, shipped/never-shipped feature flags, `# TODO` with no task, code-restating comments, unimported re-exports.

**6. One-File-One-Reason (800-line ceiling)** — a source file over **800 lines** has more than one reason to change; split it along the seam, don't grow it. This is the arbiter for the tension between sub-rules 1 and 3: *below* the ceiling, reuse the existing module and add no file; *at* the ceiling, a new sibling module is the correct change, not over-engineering. Enforced at write time by `block-bad-patterns.sh` (BLOCK on a Write that authors an oversized file; warn on an Edit that grows one) and at merge time by the per-file ratchet in `tests/test_file_size_budget.py`. Generated code, vendored trees, and data tables are exempt — the ceiling counts *hand-written reasons to change*, not lines.

## When refactoring / adding *is* justified

At least one must be true: the current code actively prevents the task (blocking edit, broken type, deadlock); three call sites converged independently; a documented incident demanded it; the user explicitly asked. Otherwise — file a task, ship the smallest fix.

## Reality check — run before any non-trivial addition

| Question | Tool |
|---|---|
| Does this already exist? | `cos_graph_query`, `cos_doc_search`, grep |
| Does this need to exist *now*? | Is there a real current caller, or is this speculation? |
| Will I remove this if the next task is canceled? | If yes, don't add it now — file a task. |
| Is this someone else's already-solved problem? | stdlib, framework, existing skill / playbook. |
| Is the abstraction earned? | Three divergent call sites — not two, not "could see three coming". |
| Could three inlined lines be clearer than one helper? | Often yes. Pick clarity. |

## Anti-patterns (reject in review, fix on sight)

New file when an existing namespace fits *and that namespace is under the 800-line ceiling* · appending to an already-oversized file because "it belongs there" · new skill/hook/rule when one already covers the matcher · a class wrapping one method that calls one external function · one-branch config switch · helper "for testability" when the original was testable · refactor bundled with a bug fix · reimplementing a stdlib function · `IFoo` with one implementation · new doc when an existing one has the scope · two skills/rules with overlapping triggers (merge them).

## Enforcement

Convention — no hook reliably detects over-engineering. Backed by self-review, code review rejecting reality-check failures, `cos_search` surfacing prior incidents, and the `clean-code` skill enforcing the tactical instances (no abbreviations, no magic numbers, no positional booleans, nesting ≤ 2).

## See also

[api-contract-discipline.md](api-contract-discipline.md) (producer shape) · [test-discipline.md](test-discipline.md) (matrix not full sweep) · [clean-code SKILL](../skills/clean-code/SKILL.md) (tactical naming) · [critical-rules.md § Rule 22](../../docs/governance/critical-rules.md#rule-22--anti-overengineering) (rationale).
