---
id: TASK-346
title: "Install resilience \u2014 survive meta-repo relocation, version skew, recovery-hint errors"
swimlane: cli
kind: bug
epic: A-install
labels: [wave-0, onboarding-program, ready]
status: icebox
priority: P0
appetite: 2d
created: 2026-06-11
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-346: Install resilience — survive meta-repo relocation, version skew, recovery-hint errors

**Outcome (one sentence):** cos survives meta-repo relocation (resilient root resolution + auto `sync-doctor --repair` path), `cos update` warns on core-version skew, and every install/init failure path (missing extras, registry write, doc-index) prints an actionable recovery hint.

## Read First
- src/cli/main.py (CODING_OS_ROOT resolution, main.py:65)
- src/cli/update.py
- src/cli/sync_all.py
- src/cli/_init_helpers.py
- src/core/scripts/install-adapter.sh (absolute symlink creation)
- src/cli/registry.py
- docs/engineering/hub-architecture.md

## Repro Steps
1. `cos init --agent claude --template python --name t1 --yes` in a temp dir, then `mv` the coding-os meta-repo directory to a new path.
2. In the consumer project run `cos update` and any hook-firing edit.
Expected: cos detects the stale root, repairs symlinks (or prints exact `cos sync-doctor --repair` instructions), and continues.
Actual: `.claude/` symlinks dangle silently, hooks/skills/rules vanish, `cos update` resolves TEMPLATES_DIR against the dead path and fails without a recovery hint.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a consumer project created by `cos init` and a meta-repo that has been moved to a new path, **When** the user runs any `cos` command in that project, **Then** the stale root is detected and either auto-repaired via the sync-doctor path or a single copy-pasteable repair command is printed (no silent dangling symlinks).
- **Given** a consumer project stamped with an older core version, **When** `cos update` runs, **Then** a version-skew warning names both versions and the migration doc.
- **Given** init/update failure paths (missing `--extra rag`/`graph_os`, registry write failure, doc-index failure), **When** each failure occurs, **Then** stderr contains an actionable recovery hint (verified by tests for each path).
- **Given** the existing test suite, **When** `uv run pytest tests/test_cli.py -q` runs, **Then** new regression tests for root-resolution + skew-warning + recovery-hints pass and no existing test breaks.

## Work Log
