---
id: TASK-102
title: "Phase L.10 — verify-suite granularity (lint only changed files instead of repo-global)"
swimlane: core
kind: chore
epic: null
labels: []
status: icebox
priority: P2
appetite: "1d"
created: 2026-04-25
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-102: Phase L.10 — verify-suite granularity (lint only changed files instead of repo-global)

**Outcome (one sentence):** Add `make docs-lint-changed` (and analogous `*-changed` targets) that lint only files in `git diff --name-only HEAD` so an unrelated broken doc cannot block an in-flight task-done in coding-os meta-repo.

## Read First
- [docs/phase-l10-plan.md](../phase-l10-plan.md)
- [scripts/docs_lint.py](../../scripts/docs_lint.py)
- [Makefile](../../Makefile)
- [core/hooks/enforce-verify.sh](../../core/hooks/enforce-verify.sh)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a meta-repo with one pre-existing broken doc (e.g. missing `Purpose:` line) AND a clean docs change in the current PR
- **When** the agent runs `make docs-lint-changed`
- **Then** lint runs only on the changed file and exits 0 — the unrelated broken doc is reported via `make docs-lint` (full sweep) only
- **And** `enforce-verify.sh` calls `docs-lint-changed` (not `docs-lint`) for the freshness check so task-done is unblocked when the agent's own changes are clean

## Work Log
