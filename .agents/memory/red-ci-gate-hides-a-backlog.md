---
name: red-ci-gate-hides-a-backlog
description: "A failing gate job skips everything downstream, so a days-old red CI accumulates hidden failures — check how long it has been red before assuming your change broke it."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6fa96ac8-74bf-4312-9d92-4b169467cec9
  modified: 2026-08-23T20:33:43.253Z
---

coding-os CI has a `Lint` job that gates the other 11. When it went red on 2026-08-17 (eslint hit 32 warnings against a `--max-warnings=30` ratchet), every downstream job reported `skipping`, not `failure`. Six days of commits merged "green" while four real failures piled up unseen:

- `from datetime import UTC` in 5 files — an ImportError on py3.10, which `requires-python = ">=3.10"` declares as supported
- the OpenAPI snapshot drifted from `docs/api/openapi.json`
- two assertions left stale by commit `ed462458`, which itself merged while CI was red
- (plus one genuinely mine)

**Why:** a gating job turns every downstream failure into a *skip*, and a skip looks like "nothing to do" in every summary view. The backlog is invisible until the gate clears, so the person who fixes the gate inherits everyone's debt at once.

**How to apply:** before diagnosing a CI failure as yours, run `gh run list --workflow=CI --branch=main --limit 12` and read the conclusion column — if it has been red for days, most of what you find is inherited. Then budget for a multi-round fix cycle rather than one push: each round only reveals the next layer. Never raise the ratchet to go green (the eslint fix was deleting two dead directives, 32→30); and note that at exactly the cap there is zero headroom, so the next warning re-breaks the release. Related: [[verification-matrix-must-match-ci]], [[run-the-feature-not-just-its-tests]].
