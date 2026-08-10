# Anti-Overengineering (Always Active)

> **Hard rule:** Solve the problem in front of you with the smallest correct change. Reuse what exists. Don't speculate. Don't duplicate. Cross-cutting — applies to every artifact (code, docs, hooks, skills, templates, tests, CLI, configs).

Why (cumulative cost of every line): [critical-rules.md § Rule 22](../../docs/governance/critical-rules.md#rule-22--anti-overengineering).

## The six sub-rules

**1. Reuse-First** (mirrors P1 SSOT-first) — before writing **anything**, search `cos_graph_query`/`cos_graph_context` (similar symbol?), `cos_search` (solved before?), `cos_doc_search` (spec exists?), grep/find (literal present?). Sibling exists → extend or reuse, never copy-paste, never reimplement a stdlib/framework primitive.

**2. No-Speculation** — build only what the current task requires. Reject "might need it later", "in case we add X", generic helpers with zero callers, one-branch config switches, `IFoo` with one implementation. Documented future work goes to `docs/tasks/`, not code.

**3. Diff-Minimal** (mirrors P4 Diff-first) — bug fix touches just the bug; no ride-along cleanup; one-shot operation gets no helper extraction; three similar lines beat a premature abstraction. Unrelated cleanup → its own task.

**4. No-Premature-Abstraction (Rule of Three)** — extract only when **three** real, divergent call sites need it. Two (or two-and-a-half)? Inline. If the parameter list is already weird at three callers, the abstraction axis is wrong.

**5. Defer-by-Default** — at task close ask "what can I remove?", not "what should I add?". Sweep for unused params, dead imports, unreferenced functions, shipped/never-shipped feature flags, `# TODO` with no task, code-restating comments, unimported re-exports.

**6. One File, One Cohesive Responsibility** — **cohesion decides, line count only backstops.** Split a file the moment a new *independently changeable* concern appears, even far below any budget; conversely, never carve arbitrary fragments just to satisfy a number — an extracted module must own a coherent responsibility and a clear boundary. Budgets for hand-written source: **≤300 LOC** preferred · **301–400** review for an extraction seam before adding substantial behavior · **401–500** growth demands strong cohesion; prefer extraction where a natural boundary exists · **>500** do not grow — split along an existing architectural seam first. A file rule alone is gameable (280 lines, one 230-line function), so the companion budgets in [clean-code](../skills/clean-code/SKILL.md) — function length, cyclomatic complexity, parameter and dependency count — carry equal weight. Enforced at write time by `block-bad-patterns.sh` and at merge time by `tests/test_file_size_budget.py` + `make check-file-size`. Exempt: generated code, vendored trees, machine-produced schemas/data, and explicitly recorded exceptions. Legacy files already over budget ratchet: unrelated changes must not grow them, substantial changes should shrink them when a safe seam exists.

## The Raptor lens — the same discipline at architecture scale

This rule governs the *size of a change*; the Raptor lens governs the *shape of the system*. SpaceX's Raptor went from a machine wrapped in visible plumbing to a compact unit where the plumbing is internalized or deleted — smaller **and** more powerful. Every generation of this kernel must carry **more capability per moving part, never more parts per capability**. Apply it whenever you design or review a subsystem, adapter, hook set, or refactor:

1. **Consolidate components** — "do these two modules ever change independently? If not, why are they two?" (thinking_os / graph_os / board_os share one MCP process; one hook registry renders per adapter.)
2. **Zero-overhead abstractions** — "does this interface make the caller's code shorter, or just relocate the complexity?" (`ok()`/`fail()` is one contract over ~140 tools.)
3. **Delete parasitic complexity** — "if I remove this, what actually breaks — a behavior, or only a feeling of safety?" Prose that restates a hook-enforced rule is duplicate mass; two nudges with overlapping triggers should merge.
4. **Internalize and cohere** — "can this unit be tested and reasoned about without loading its neighbors?" Behavior lives where its data lives; leaf modules import no siblings.

A design that *adds* parts must name the capability paying for each one, and prefers deleting a seam over documenting it. Full lens + the worked case study + the engine photo: [raptor-consolidation.md](../../docs/architecture/raptor-consolidation.md). Cite it in the work log when a decision rests on one of the four.

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

New file for a fragment with no responsibility of its own (splitting to hit a number, not a seam) · appending an independently changeable concern to an existing file because "it belongs there" · new skill/hook/rule when one already covers the matcher · a class wrapping one method that calls one external function · one-branch config switch · helper "for testability" when the original was testable · refactor bundled with a bug fix · reimplementing a stdlib function · `IFoo` with one implementation · new doc when an existing one has the scope · two skills/rules with overlapping triggers (merge them).

## Enforcement

Convention — no hook reliably detects over-engineering. Backed by self-review, code review rejecting reality-check failures, `cos_search` surfacing prior incidents, and the `clean-code` skill enforcing the tactical instances (no abbreviations, no magic numbers, no positional booleans, nesting ≤ 2).

## See also

[api-contract-discipline.md](api-contract-discipline.md) (producer shape) · [test-discipline.md](test-discipline.md) (matrix not full sweep) · [clean-code SKILL](../skills/clean-code/SKILL.md) (tactical naming) · [critical-rules.md § Rule 22](../../docs/governance/critical-rules.md#rule-22--anti-overengineering) (rationale).
