---
name: run-the-feature-not-just-its-tests
description: Supervised dispatch passed 1599 unit tests while being completely unable to run; three blocking defects only appeared when a real sub-agent was actually spawned.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 1a1fdfc1-4bec-46ac-8585-4aef5326a19d
  modified: 2026-08-18T06:30:49.460Z
---

On 2026-08-18 the supervision/dispatch subsystem had been "enabled" for six days
with 1599 green `thinking_os` tests and zero working dispatches. Every defect
that mattered was invisible to the suite and appeared within minutes of running
`dispatch_request` for real:

1. **Tier alias rejected at validation.** Roles declare `model_pref: {complicated:
   sonnet}`; descriptors declare `claude-sonnet-5`. Core validated *before* the
   adapter resolved the alias, so every routed tier failed `model 'sonnet' is not
   declared by adapter 'claude'`. No supervised dispatch with a `model_pref`
   could ever have run. The tests mocked the dispatcher, so nothing exercised
   the validation branch against a real descriptor.
2. **Failed dispatches recorded nothing.** Persistence guarded on
   `status in ("ok","timeout")`. A run that burned 271s of tokens left no row —
   so a chronically broken route and an idle one both reported zero.
3. **Error rows carried a NULL message.** The insert read `meta.error` while the
   dispatcher held `result.error`, so an error row recorded *that* something
   failed while discarding *what*.

**Why:** the operator asked "is this actually being used?" — and the honest answer
needed evidence, not a passing suite. Critical Rule 26 says verify by executing;
this is the case that shows *why*: unit tests pinned the parts, and the parts
were individually correct while the composition could not run at all.

**How to apply:** for any feature with a toggle, treat "enabled + green tests" as
unverified until one real end-to-end run is observed and its side effect is read
back from the store. Add a doctor-style check that compares the toggle against
evidence of use (`supervision.routing_exercised` does this) — an enabled feature
that never fires otherwise looks identical to a disabled one. See also
[[dry-run-in-repo-before-trusting-units]] and [[fail-open-hooks-hide-dead-triggers]],
which are the same failure in the CLI and hook layers.
