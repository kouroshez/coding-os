---
name: rules-edits-need-golden-capture
description: Editing src/core/rules/** or src/core/hooks/** renders into tests/golden — run make golden-capture or CI fails on 8 sections.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 5ac9fe2e-f9a3-4490-bb81-1ab2bb139298
  modified: 2026-09-18T21:47:26.286Z
---

Any edit under `src/core/rules/**`, `src/core/skills/**` or `src/core/hooks/**` is copied verbatim into `tests/golden/{claude,codex}_{base,django,nextjs,node-express,vue-nuxt}`. Change one line — even a number inside prose — and `test_golden_parity` fails on 8 sections in CI while `make docs-lint` passes locally.

**Why:** the local gate a `.md` path matches is docs-lint, which knows nothing about the golden copies. AGENTS.md warns about this explicitly ("Rule 10 with a `.md` disguise"), and I still hit it twice in one week: once editing hooks, once changing "~4,850 tests" to the measured "~8,510" in `test-discipline.md`.

**How to apply:** after touching those trees, run `make golden-capture` (~3 min, 8 sections) and commit `tests/golden/` in the same change. Cheap pre-check before pushing: `uv run pytest tests/test_golden_parity.py -q`. The capture also invalidates the verify ledger, so re-run `make verify-hooks` / `make docs-lint` right before committing or `enforce-verify.sh` blocks it. Related: [[verification-matrix-must-match-ci]], [[fix-the-twin-of-every-guard-you-fix]].
