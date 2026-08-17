---
name: fail-open-hooks-hide-dead-triggers
description: "A fail-open hook that swallows its helper's error looks identical to a legitimate no-op; its debounce marker then makes one failure permanent."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 1a1fdfc1-4bec-46ac-8585-4aef5326a19d
  modified: 2026-08-17T07:52:43.097Z
---

When a coding-os hook delegates to a Python helper and fails open, a helper that
**could not even import** produces the same observable result as a helper that
correctly decided to do nothing: empty stdout, exit 0, and a log line saying
`ok`. Three separate triggers in this repo were dead for weeks this way
(`auto-compose-roles` producing no chain because `formula_composer` needs
pydantic and the hook ran bare `python3`; `model_routing` enabled but never
resolved; single-dispatch guarded on an error string CPython never emits).

**Why:** fail-open is correct for a hook — it must never block a prompt — but
"never block" was implemented as "never distinguish". The debounce marker made it
worse: it was stamped *before* checking the child's exit code, so a single failed
run silenced every retry for the rest of the session, and the marker's existence
read as evidence the work had happened.

**How to apply:**
- Run helpers through `cos_resolve_python` (`_cos_env_io.sh`), never bare
  `python3` — bare `python3` lacks the project's dependencies. Only
  `cos_resolve_python` sees pydantic, `formula_composer`, `_supervision_policy`.
- Capture the child's rc (`set +e` / `HELPER_RC=$?`) and log a breadcrumb via
  `cos_log_hook <hook> warn "helper rc=…"` on non-zero, so it surfaces in
  `cos hooks-log` instead of vanishing.
- **Stamp the debounce marker only after rc == 0.** A failed run must stay
  retryable.
- Have the helper return a distinct non-zero rc for "I could not import my
  dependencies" so that case is separable from "nothing to do".
- Verify a trigger by asserting its *side effect* exists (the state file it
  writes), not by asserting the hook exited 0. Related: [[dry-run-in-repo-before-trusting-units]].
