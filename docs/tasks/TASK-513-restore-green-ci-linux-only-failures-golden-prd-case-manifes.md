---
id: TASK-513
title: "Restore green CI \u2014 Linux-only failures: golden PRD case + manifest changes.log drift + real_embeddings model-skip"
swimlane: infra
kind: bug
epic: null
labels: [ci, release-unblock, case-sensitivity, manifest, embeddings, ready]
status: complete
priority: P0
appetite: 1d
created: 2026-06-22
started: 2026-06-22
completed: 2026-08-02
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-513: Restore green CI — Linux-only failures: golden PRD case + manifest changes.log drift + real_embeddings model-skip

**Outcome (one sentence):** CI pytest + modularity + verification-matrix jobs pass on a clean Linux checkout so CI Pass goes green and release PR #29 can merge.

## Read First
- src/core/runtime_paths.yaml
- src/scripts/generate_manifest.py
- src/core/thinking_os/tests/conftest.py
- src/scripts/capture_golden.py

## Repro Steps
Clean clone on case-sensitive FS (or Linux CI), then run: `uv run pytest tests/test_golden_parity.py` (6 fail: docs/PRD vs docs/prd), `uv run pytest tests/test_doctor.py` (4 fail: manifest_fresh missing changes.log), `uv run --extra rag pytest src/core/thinking_os/tests/` (5 fail: real_embeddings return 0 results offline).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a clean case-sensitive clone, **When** test_golden_parity runs, **Then** all 8 sections pass (golden docs/prd lowercase matches the fresh render).
- **Given** a clean clone, **When** test_doctor manifest_fresh runs, **Then** no expected file is missing (changes.log excluded via runtime_paths.yaml SSOT).
- **Given** CI offline with no vendored model, **When** real_embeddings-marked tests run, **Then** they skip rather than fail.

## Work Log
- 2026-06-22 [claude]: Edit conftest.py
- 2026-06-22 [claude]: Edit runtime_paths.yaml
- 2026-06-22 [claude]: commit f8c000a792 — fix(ci): rename golden docs/PRD to docs/prd — case bug fails parity on Linux
- 2026-06-22 [claude]: commit b4836b2492 — test(ci): skip real_embeddings tests when the model is unavailable offline
- 2026-06-22 [claude]: Edit test_golden_parity.py
- 2026-06-22 [claude]: commit 548e62c4bf — fix(ci): exclude .coding-os/ + settings.local from golden parity check
- 2026-06-22 [claude]: All 4 root causes fixed + verified on a clean case-sensitive APFS clone (CI-equivalent): golden PRD→prd rename +…
- 2026-06-22 [claude]: commit 0aa607d6c3 — chore(board): add TASK-513 (restore green CI — Linux-only failures)
- 2026-06-22 [claude]: commit 8567453e47 — chore(board): TASK-513 → testing + verification work-log
- 2026-06-22 [claude]: Edit generate_manifest.py
- 2026-06-22 [claude]: Edit runtime_paths.yaml
- 2026-06-22 [claude]: Edit .gitignore
- 2026-06-22 [claude]: Edit subsystems.yaml
- 2026-06-22 [claude]: Edit test_cli.py
- 2026-06-22 [claude]: Edit test_cli.py
- 2026-06-22 [claude]: commit 6a36e1d2a6 — fix(ci): commit changes.log as a seeded scaffold file (gitignore swallowed it)
- 2026-06-22 [claude]: commit bbd10d3adc — fix(ci): exclude __pycache__/.pyc from scaffold manifest + regen
- 2026-06-22 [claude]: commit 933648ed65 — fix(ci): give warn-destructive-edit a module owner (kernel) — F9 invariant
- 2026-06-22 [claude]: Edit ci.yml
- 2026-06-22 [claude]: Edit ci.yml
- 2026-06-22 [claude]: Edit ci.yml
- 2026-06-22 [claude]: commit 286138a46c — ci: move macOS matrix to nightly-only + skip CI on board-sync commits
- 2026-06-22 [claude]: Edit test_branding.py
- 2026-06-22 [claude]: Edit test_no_phantom_tool_refs.py
- 2026-06-22 [claude]: Edit test_link_commit_to_task.py
- 2026-06-22 [claude]: Edit test_hub_settings_model_routing.py
- 2026-06-22 [claude]: commit ea738e4c99 — test(ci): fix pre-existing tests/ failures unmasked once the pytest gate went green
- 2026-06-22 [claude]: Edit ci-red-masking-cascade.md
- 2026-06-22 [claude]: Edit github-actions-cost-macos-10x.md
- 2026-06-22 [claude]: Edit dev-pollution-leaks-into-manifest.md
- 2026-06-22 [claude]: Edit MEMORY.md
- 2026-06-22 [claude]: CI was red across MANY masked layers; all fixed + verified locally (zero GitHub minutes). Recent: docs-lint links,…
- 2026-08-02 [claude]: Edit scaffold-verify.yml
- 2026-08-02 [claude]: Edit scaffold-verify.yml
- 2026-08-02 [claude]: commit fe32399c57 — ci: set SV_DIR per-job — runner context is invalid at workflow-level env
- 2026-08-02 [claude]: committed 135cfaf8 · 2 files
- 2026-08-03 [claude]: All 3 acceptance classes verified fixed ON CI: golden parity green (modularity job), manifest green…
