---
name: test-isolation-that-deletes-is-not-isolation
description: Unsetting an env var a tool DERIVES from is the opposite of isolation — it routes tests at the live project.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 5ac9fe2e-f9a3-4490-bb81-1ab2bb139298
  modified: 2026-09-18T23:23:24.397Z
---

`tests/conftest.py` scrubbed `COS_STATE_DIR` from the environment to keep tests hermetic. But `cos-env.sh` **derives** that path from the repo root when it is absent, so every hook a test spawned wrote into the live `.coding-os/`.

Measured damage: 3,095 `rule=pr-*` rows in `log_events` for a repo where pr-mode is off, four false `learned_patterns` injected into every session as guidance, and `runtime.recent_errors` counting test-generated policy blocks as faults. One leak, three diagnostics lying.

**Why:** deletion only isolates a variable the tool treats as an override. If the tool has a fallback, deleting hands it the fallback — which is usually production.

**How to apply:** point it at `tmp_path_factory.mktemp(...)`, never delete it. Then expect fallout in exactly the tests that assert the *derivation* — four of them here (`test_default_state_dir`, two config-route dogfood tests, a codex adapter test). Those must drop the var themselves; fix the test, not the fixture. An autouse fixture change means the whole suite is the blast radius: run `pytest tests/ -q -m 'not slow'` before pushing, because CI does, and it caught four failures a targeted run missed. Related: [[capture-the-payload-never-assume-it]], [[run-the-feature-not-just-its-tests]].
