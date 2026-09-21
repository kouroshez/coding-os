---
name: measure-the-system-not-its-display-budget
description: "Grading a tool's accuracy on its user-facing response measures the token trimmer; read the full internal result instead."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 5ac9fe2e-f9a3-4490-bb81-1ab2bb139298
  modified: 2026-09-21T02:36:37.222Z
---

When measuring how *complete* a retrieval system's answer is, grade what the system **knows**, not what its response returned. The graph's `references` envelope returned 60 of a known 185 call sites for `GraphNode` because the token-budget trimmer cut the row list, so the first recall figure — 0.297 — was describing the page size. Reading every edge under the tool's own kind defaults put it at 0.496.

**Why:** the failure inverts the metric. A *tighter* token budget would have scored as a *worse* graph, which is precisely the "cheaper looks better" confusion an accuracy oracle exists to remove. It is invisible without a check, because both numbers are plausible and nothing errors. The tell was two different symbols both reporting exactly 60 sites.

**How to apply:** before dividing by anything, print the numerator and denominator for one item and ask what each is a count *of*. Round, identical counts across unrelated inputs mean a cap, not a measurement. Keep the cost measurement on the real response (that is what the caller pays) and the accuracy measurement on the full internal result — they are different questions and should read different sources. Same shape as [[run-the-feature-not-just-its-tests]]: the surface that looks like the system is not the system. Related: [[measure-per-profile-never-summed]].
