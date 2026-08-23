---
name: fix-the-twin-of-every-guard-you-fix
description: A persistence guard was widened on the single-dispatch path days ago; its copy on the parallel path stayed narrow and kept dropping failed runs.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 1a1fdfc1-4bec-46ac-8585-4aef5326a19d
  modified: 2026-08-21T04:54:28.205Z
---

On 2026-08-18 the dispatch persistence guard was widened from `status == "ok"`
to `("ok","timeout","error")` so a failed run would leave a row. On 2026-08-21 an
audit found `cos_dispatch_parallel_run` still carried the original
`outcome.status == "ok"` — the same condition, hand-copied, one function below
the fixed one in the same file. A fan-out where four of five roles failed left
one row, so a chronically broken route inside a parallel layer read identically
to a layer nobody ran.

The unit suite (1605 green) never saw it: the parallel path had no test that
dispatched a failing leg at all.

**Why:** the first fix was verified by executing the *single* path and reading
the row back, which is exactly the discipline that catches real bugs — and it
still missed this one, because verification proves the path you ran, not the
path you didn't.

**How to apply:** after fixing any guard, literal, or status set, grep the
repo for the *condition*, not the function name (`grep -n 'status == "ok"'`),
before calling it done. When two copies are found, collapse them into one named
constant in the same commit — the duplication is the defect, the drift is only
its symptom. Then write the regression test and **prove it fails without the
fix** by reverting the line and re-running; a regression test that passes either
way records nothing. See also [[run-the-feature-not-just-its-tests]].
