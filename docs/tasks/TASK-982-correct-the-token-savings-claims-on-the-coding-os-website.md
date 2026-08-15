---
id: TASK-982
title: "Correct the token-savings claims on the coding-os website"
swimlane: docs
kind: bug
epic: honest-benchmarks
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-15
started: 2026-08-15
completed: 2026-08-15
agent_session: ses-claude-20260814-120316-413b
depends_on: []
blocked_by: []
references: []
---
# TASK-982: Correct the token-savings claims on the coding-os website

**Outcome (one sentence):** The public landing page and the synced docs on coding-os.dev carry the same corrected, reproducible numbers as the repo, so a visitor cannot find a claim the repo has already retracted.

## Read First
- /Users/ciro/Files/Project/cos-website/src/frontend/app/(marketing)/landing-sections.tsx
- /Users/ciro/Files/Project/cos-website/src/frontend/scripts/sync-docs.mjs
- README.md

## Repro Steps
cos-website/src/frontend/app/(marketing)/landing-sections.tsx lines 99 and 196 hardcode "≈ 98% fewer tokens", sourced from the README row that is being corrected. content/docs is a build-time copy of the repo docs via scripts/sync-docs.mjs, so stale claims also live in graph-use-cases.md and graph-hallucination-cures.md until re-synced.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** the marketing landing page, **When** it renders, **Then** it carries no savings figure that the repo has retracted, and any figure it does carry names its baseline.
- **Given** the synced docs tree, **When** the site is built, **Then** it reflects the corrected repo docs rather than the pre-correction copies.
- **Given** the site's own planning docs (prd, build-checklist), **When** they cite the benchmark, **Then** they cite the corrected numbers.
- **Given** the site build, **When** it runs after the edits, **Then** it passes lint, typecheck and unit tests.

## Work Log
- 2026-08-15 [claude]: Landing page now quotes ~78% against the grep-windows baseline instead of 98% against read-everything, and the…
- 2026-08-15 [claude]: Status transitioned to complete via cos task-done.
