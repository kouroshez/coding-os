---
id: TASK-598
title: "factory-standard v2 rows + stack-lint soft checks (anatomy, runnable-manifest, lint-config, reference-integrity)"
swimlane: cli
kind: feature
epic: stack-factory-v2
labels: [ready]
status: archive
priority: P2
appetite: 2d
created: 2026-06-27
started: 2026-06-26
completed: 2026-06-27
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-598: factory-standard v2 rows + stack-lint soft checks (anatomy, runnable-manifest, lint-config, reference-integrity)

**Outcome (one sentence):** The 12-row TASK-361 factory contract gains rows for runtime-manifest/lint-config/sample-test/reference-integrity/CI/container, and `stack_lint.py` reports them as SOFT GAPs (exit 0) so the standard itself is complete and every real gap is auditable. SSOT-first fix that stops the gap recurring per-stack and defines the bar that T4-T12 fill.

## Read First
- docs/playbooks/template-authoring.md
- src/cli/stack_lint.py
- docs/governance/anatomy-contract.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the factory-contract table in docs/playbooks/template-authoring.md, **When** updated, **Then** it documents rows 13-18: runtime-manifest, lint-config, sample-test, reference-integrity, cicd-workflow, containerization (each marked hard/soft).
**Given** src/cli/stack_lint.py, **When** extended, **Then** it adds SOFT checks: anatomy.md present when SKILL.md directs reading it; a buildable manifest in structure.root for code categories; a lint config present where a verify command names a linter; every `rules:` and DOMAIN_ROUTES path resolves on disk.
**Given** all new checks are SOFT, **When** `cos stack-lint` runs across all stacks, **Then** it prints the GAP lines but exits 0 (no hard block until backfill completes).
**Then** `uv run pytest tests/test_cli.py -q` and `make docs-lint` are green.

## Work Log
- 2026-06-27 [claude]: Edit stack_lint.py
- 2026-06-27 [claude]: Edit stack_lint.py
- 2026-06-27 [claude]: Edit stack_lint.py
- 2026-06-27 [claude]: Edit backend.md
- 2026-06-27 [claude]: Edit frontend.md
- 2026-06-27 [claude]: Edit backend.md
- 2026-06-27 [claude]: Edit stack_lint.py
- 2026-06-27 [claude]: Edit template-authoring.md
- 2026-06-27 [claude]: Edit frontend.md
- 2026-06-27 [claude]: Edit _init_helpers.py
- 2026-06-27 [claude]: Edit _init_helpers.py
- 2026-06-27 [claude]: Edit _init_helpers.py
- 2026-06-27 [claude]: Edit check_gitignore.py
- 2026-06-27 [claude]: Added 4 SOFT stack-lint checks (runtime-manifest, lint-config, reference-integrity, anatomy; exit 0) + factory rows…
- 2026-06-27 [claude]: Status transitioned to complete via cos task-done.
