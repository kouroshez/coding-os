---
name: measure-per-profile-never-summed
description: Publish coding-os cost/benefit per project profile with a named baseline — never a summed total or a strawman comparison.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: db0f3780-7625-4641-9033-0cbc5a01ec6d
  modified: 2026-08-15T12:15:30.280Z
---

Kourosh rejected any single "coding-os costs N tokens" figure: consumer projects
install different stacks, so a WordPress project and a polyglot one do not pay the
same, and summing every skill/stack in the meta-repo misrepresents both. The same
standard applies to benefit claims — a savings percentage must name the baseline
it beat, and that baseline must be what a competent agent would actually do.

**Why:** the project was publicly reviewed and the inflated figures were the thing
reviewers seized on. A number that cannot survive a skeptic is worse than no
number, because it puts every honest claim beside it under suspicion.

**How to apply:** measure by executing (`src/scripts/context_budget.py` for cost,
`src/core/graph_os/bench/third_party.py --baseline grep-windows` for benefit),
publish the spread and the worst case, and state the cases where the tool loses —
that disclosure is what makes the rest credible. Related: [[no-parking-actionable-findings]].
