---
id: TASK-961
title: "Supply-chain posture: lift OpenSSF Scorecard from 5.9 and clear CodeQL/OSV/Dependabot findings"
swimlane: infra
kind: chore
epic: null
labels: [supply-chain, ci, scorecard, ready]
status: complete
priority: P1
appetite: 3d
created: 2026-08-13
started: 2026-08-13
completed: 2026-08-13
agent_session: ses-claude-20260812-170221-1654
depends_on: []
blocked_by: []
references: []
---
# TASK-961: Supply-chain posture: lift OpenSSF Scorecard from 5.9 and clear CodeQL/OSV/Dependabot findings

**Outcome (one sentence):** Scorecard aggregate rises from 5.9 toward ~8.5 by fixing the checks that are actually fixable (Pinned-Dependencies, Vulnerabilities, Fuzzing, Signed-Releases provenance, SAST, CII badge), the 66 real CodeQL alerts are triaged and the exploitable ones fixed, and both open Dependabot alerts are closed. Checks structurally unfixable for a solo trunk-based repo (Code-Review, Contributors, Maintained) are documented with the honest reason rather than gamed.

## Work Log
- 2026-08-13 [claude]: Edit pom.xml
- 2026-08-13 [claude]: Edit pom.xml
- 2026-08-13 [claude]: Edit osv-scanner.toml
- 2026-08-13 [claude]: commit c7cab878fe — fix(deps): clear all 79 OSV advisories across scaffolds and locks
- 2026-08-13 [claude]: commit 5d32f110b3 — ci: pin all 48 GitHub Action refs by commit SHA
- 2026-08-13 [claude]: Edit release-please.yml
- 2026-08-13 [claude]: Edit release-please.yml
- 2026-08-13 [claude]: Edit release-please.yml
- 2026-08-13 [claude]: commit 0efb0808af — ci: publish the SLSA provenance bundle as a release asset
- 2026-08-13 [claude]: commit c596947b79 — fix(web): escape quotes and gate URL schemes in the task markdown renderer
- 2026-08-13 [claude]: Edit logs.py
- 2026-08-13 [claude]: Edit logs.py
- 2026-08-13 [claude]: Edit _mcp_forge.py
- 2026-08-13 [claude]: commit ba37021f9e — fix(security): close the weak-hash, ReDoS and URL-substring CodeQL alerts
- 2026-08-13 [claude]: Edit ci-gates.md
- 2026-08-13 [claude]: commit 41288b0cfa — docs(ci-gates): record the Scorecard weight model and its honest ceiling
- 2026-08-13 [claude]: Edit conftest.py
- 2026-08-13 [claude]: Edit conftest.py
- 2026-08-13 [claude]: commit c2dc381ef0 — refactor: clear the SIM105, SIM102 and E741 burndown ignores (#30, #31, #32)
- 2026-08-13 [claude]: commit c51ecea59a — docs(bench): publish the Django 5.2 third-party token-cost row (#37)
- 2026-08-13 [claude]: commit a63730e985 — build: pin Docker base images by digest and the release build backend
- 2026-08-13 [claude]: commit bbb39fd003 — fix(ci): set the mypy baseline from the CI count, not the local one
- 2026-08-13 [claude]: commit 0ba7044638 — test: scrub ambient COS_* derived paths in conftest instead of per-site (#39)
- 2026-08-13 [claude]: commit b67047117b — fix(web): drop the control-char regex class that broke the ESLint gate
- 2026-08-13 [claude]: Scorecard 5.9 -> 7.4 verified from the live API on c51ecea5 (Vulnerabilities 0->10, Fuzzing 0->10,…
- 2026-08-13 [claude]: Edit ci-gates.md
- 2026-08-13 [claude]: commit 7dc5ce4592 — docs(ci-gates): record the measured 5.9 to 7.4 outcome, not the prediction
- 2026-08-13 [claude]: Status transitioned to complete via cos task-done.
