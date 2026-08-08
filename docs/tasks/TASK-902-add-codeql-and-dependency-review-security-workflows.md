---
id: TASK-902
title: "Add CodeQL and dependency-review security workflows"
swimlane: core
kind: security
epic: null
labels: [ci, supply-chain, ready]
status: complete
priority: P1
appetite: 2h
created: 2026-08-08
started: 2026-08-07
completed: 2026-08-08
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-902: Add CodeQL and dependency-review security workflows

**Outcome (one sentence):** CodeQL (python+js-ts) and dependency-review run on GitHub

## Read First
- docs/playbooks/security-review.md

## Threat Model
- **Attacker:** upstream package author or account-takeover publishing a malicious/vulnerable dependency; contributor introducing an injectable code path.
- **Asset:** consumer projects that install coding-os (live-symlink blast radius) + maintainer credentials in CI.
- **Attack vector:** a PR bumping to a known-CVE dependency merged unnoticed; injectable Python/TS patterns landing on main without static analysis.
- **Mitigation:** CodeQL static scan (python + javascript-typescript) on push/PR/weekly; dependency-review action blocks PRs introducing known-vulnerable packages. Both read-only permissions except security-events write.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** .github/workflows\n- **When** a push/PR lands on main\n- **Then** CodeQL analyze and dependency-review jobs run green

## Work Log
- 2026-08-08 [claude]: Edit TASK-902-add-codeql-and-dependency-review-security-workflows.md
- 2026-08-08 [claude]: Edit codeql.yml
- 2026-08-08 [claude]: Edit dependency-review.yml
- 2026-08-08 [claude]: Edit .gitignore
- 2026-08-08 [claude]: Edit ci.yml
- 2026-08-08 [claude]: Edit ci.yml
- 2026-08-08 [claude]: Edit ci.yml
- 2026-08-08 [claude]: Matched repo idiom (version-tag actions, paths-ignore docs/tasks) over SHA-pinning to keep dependabot flow…
- 2026-08-08 [claude]: Edit learning.py
- 2026-08-08 [claude]: Edit test_file_size_budget.py
- 2026-08-08 [claude]: Edit stack_registry.py
- 2026-08-08 [claude]: Edit stack_registry.py
- 2026-08-08 [claude]: Edit Makefile
- 2026-08-08 [claude]: commit f94f34b984 — test(quality): add file-size ratchet gate capping tracked python files at 5700 lines
- 2026-08-08 [claude]: commit 7caea1ed35 — fix(lint): clear the ruff baseline and fix bug-prone patterns
- 2026-08-08 [claude]: commit d1ae7e2a20 — ci: make ruff check blocking, add coverage gate job, key caches on committed uv.lock
- 2026-08-08 [claude]: Status transitioned to complete via cos task-done.
