---
id: TASK-889
title: "Secret-fixture policy \u2014 declare, structure and enforce why detector test data is safe"
swimlane: core
kind: security
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-05
started: 2026-08-04
completed: 2026-08-04
agent_session: ses-claude-20260803-180632-5fca
depends_on: []
blocked_by: []
references: []
---
# TASK-889: Secret-fixture policy — declare, structure and enforce why detector test data is safe

---
id: TASK-889
title: "Secret-fixture policy — declare, structure and enforce why detector test data is safe"
swimlane: core
kind: security
epic: null
labels: [ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-08-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-889: Secret-fixture policy — declare, structure and enforce why detector test data is safe

**Outcome (one sentence):** A contributor or security researcher can verify from the repository alone — without asking a maintainer — that every credential-shaped string in the tree is synthetic test data, and the rule that keeps it that way is enforced by a test rather than by reviewer memory.

## Read First
- `src/core/hooks/block-secrets.sh` — the detector these fixtures exist to exercise
- `tests/test_block_secrets.py` — already does the right thing (runtime-composed literals)
- `src/core/thinking_os/tests/test_sanitizer.py`, `tests/test_hooks.py` — fixture sites with bare literals
- `SECURITY.md` — where the policy belongs

## Threat Model
- **Attacker:** none directly — this is an assurance and trust defect, not an exploitable one.
- **Asset:** the project's credibility with contributors, downstream adopters and security researchers, plus reviewer attention (alert fatigue).
- **Vector:** a credential-shaped literal in a public repo produces a real secret-scanning alert. Resolving it in the GitHub UI records the reasoning where only maintainers can see it, so an outside reader cannot distinguish "synthetic fixture" from "leaked and dismissed". A future contributor writing a new detector test has no stated rule and re-introduces a scannable literal.
- **Mitigation:** declare the fixture paths to the scanner in-repo (`.github/secret_scanning.yml`), keep every fixture structurally unscannable (runtime-composed, sub-threshold, or vendor-reserved), state the rule in `SECURITY.md`, annotate each fixture site, and enforce it with a test.
- **Residual risk:** `paths-ignore` suppresses scanning for those paths, so a real credential pasted into a test file would not alert. Bounded by keeping the ignore list to detector-fixture paths only, and by `block-secrets.sh` + the git `pre-commit` hook still scanning every commit.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the public repository and no maintainer to ask,
- **When** a contributor reads `SECURITY.md` and `.github/secret_scanning.yml` and greps the fixture sites,
- **Then** every credential-shaped string is provably synthetic by construction, and a new test fails if anyone commits a literal that would match a real vendor's scanner pattern.

## Work Log
- 2026-08-05 [claude]: Edit secret_scanning.yml
- 2026-08-05 [claude]: Edit SECURITY.md
- 2026-08-05 [claude]: Edit test_secret_fixture_policy.py
- 2026-08-05 [claude]: Edit test_tool_failure_capture.py
- 2026-08-05 [claude]: Edit block-secrets.sh
- 2026-08-05 [claude]: Edit test_block_secrets.py
- 2026-08-05 [claude]: Edit test_sanitizer.py
- 2026-08-05 [claude]: Edit test_hooks.py
- 2026-08-05 [claude]: Edit test_session.py
- 2026-08-05 [claude]: commit bad64a7671 — fix(security): declare and enforce why credential-shaped test fixtures are safe
- 2026-08-05 [claude]: Closing the alert put the reasoning where only maintainers could see it — the assurance gap the owner called out.…
- 2026-08-05 [claude]: Status transitioned to complete via cos task-done.
