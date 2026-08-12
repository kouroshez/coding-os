---
id: TASK-939
title: "feat: cos update and cos doctor tell the consumer the real package-upgrade command"
swimlane: cli
kind: feature
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-12
started: 2026-08-11
completed: 2026-08-11
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-939: feat: cos update and cos doctor tell the consumer the real package-upgrade command

**Outcome (one sentence):** A consumer running an older coding-os learns from `cos update` and `cos doctor` that a newer release exists and is given the exact package-upgrade command, instead of being told to run a command that cannot change the installed version.

## Read First
- src/cli/update.py
- src/cli/core_version.py
- src/cli/doctor_checks_core.py
- docs/governance/release-process.md

## Repro Steps
`cos update` performs zero network calls: it re-links assets from the *already installed* package. `cos doctor`'s `core.version_stamp` check emits "core drift … run `cos update`" — but `cos update` re-stamps the project to the installed version without changing it, so the advice silences the warning instead of fixing the drift. `uv tool upgrade` appears **zero** times in the repo; the README documents only the developer path (`git clone` + `uv tool install --editable .`), never `uv tool install coding-os` from PyPI, even though release-please publishes the wheel via Trusted Publishing.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** an installed coding-os older than the newest PyPI release **When** `cos update` runs **Then** it names the newer version and prints the exact package-upgrade command.
**Given** no network or a slow index **When** `cos update` runs **Then** the check is skipped without an error and the asset sync still applies.
**Given** a core-version drift **When** `cos doctor` reports it **Then** the remediation names the package-upgrade command, not only `cos update`.

## Work Log
- 2026-08-12 [claude]: Edit core_version.py
- 2026-08-12 [claude]: Edit update.py
- 2026-08-12 [claude]: Edit update.py
- 2026-08-12 [claude]: Edit update.py
- 2026-08-12 [claude]: Edit doctor_checks_core.py
- 2026-08-12 [claude]: Edit doctor_checks_core.py
- 2026-08-12 [claude]: Edit core_version.py
- 2026-08-12 [claude]: Edit update.py
- 2026-08-12 [claude]: Edit update.py
- 2026-08-12 [claude]: Edit test_core_version_release_check.py
- 2026-08-12 [claude]: Edit test_core_version_release_check.py
- 2026-08-12 [claude]: Edit test_core_version_release_check.py
- 2026-08-12 [claude]: Edit README.md
- 2026-08-12 [claude]: Edit install.sh
- 2026-08-12 [claude]: commit 16f38a5acc — feat(cli): tell consumers which command actually upgrades coding-os
- 2026-08-12 [claude]: 304 CLI tests + 10 new release-check tests green; cos doctor now prints the package-upgrade command;…
- 2026-08-12 [claude]: Status transitioned to complete via cos task-done.
