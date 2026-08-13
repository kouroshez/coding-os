---
id: TASK-959
title: "Define the release-merge trigger and correct the pre-1.0 bump table"
swimlane: infra
kind: docs
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-13
started: 2026-08-12
completed: 2026-08-12
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-959: Define the release-merge trigger and correct the pre-1.0 bump table

**Outcome (one sentence):** release-process.md names a concrete trigger for merging the standing release PR, states the real pre-1.0 bump semantics, makes the 1.0 criterion-1 gate satisfiable, and records the untagged-release gap with its exact remediation.

## Read First
- docs/governance/release-process.md
- release-please-config.json

## Delivered
- **Merge trigger** — replaced the undefined "when ready to cut" with a substance-based rule (`feat`/`fix` that changes what `cos` does for an installed user), plus why substance and not a calendar, plus the three named industry models.
- **Bump table corrected** — it claimed `feat` → minor and `refactor` → no release. Both wrong: `bump-patch-for-minor-pre-major` makes `feat` a patch (verified: 0.3.13 carried 11 `feat` commits and bumped patch), and `refactor` is not hidden in `changelog-sections` so it opens a release PR on its own.
- **1.0 criterion 1 was a trap** — "stable across ≥2 minors" demanded two breaking-change cycles as proof that breaking had stopped, since pre-1.0 only a break bumps minor. Restated as ≥10 consecutive releases **and** ≥8 weeks.

## Not delivered — needs a maintainer, not an agent
`0.3.2` / `0.3.3` / `0.3.4` are on PyPI with no git tag, so those artifacts cannot be rebuilt from source. Their release commits are identified and verified (`747a3a4e`, `a359555c`, `3bdcd867` — each checked against `pyproject.toml` *and* `.release-please-manifest.json`). Pushing the tags is rejected: `GH013 … Cannot create ref due to creations being restricted`, from a ruleset that `/rulesets` does not list even for an admin token. That restriction is Hard rule 2 enforced at the platform level and was **left in place rather than loosened** — routing around it via the Releases API would be circumvention, and creating retroactive GitHub Releases would notify watchers about weeks-old versions. Unblock: allow the three creations once in Settings → Rules, or accept the gap. Documented in release-process.md § Operational notes with a one-liner that checks the tag/PyPI invariant.

## Work Log
- 2026-08-13 [claude]: Edit release-process.md
- 2026-08-13 [claude]: Edit release-process.md
- 2026-08-13 [claude]: Edit release-process.md
- 2026-08-13 [claude]: Edit release-process.md
- 2026-08-13 [claude]: Edit release-process.md
- 2026-08-13 [claude]: Edit release-process.md
- 2026-08-13 [claude]: Edit release-process.md
- 2026-08-13 [claude]: Edit release-process.md
- 2026-08-13 [claude]: merge trigger written; bump table corrected (feat=patch, refactor releasable); 1.0 criterion-1 trap fixed; tag…
- 2026-08-13 [claude]: commit fb006ca477 — docs(release): define the merge trigger and correct the pre-1.0 bump table
- 2026-08-13 [claude]: Status transitioned to complete via cos task-done.
