---
id: TASK-513
title: "Restore green CI \u2014 Linux-only failures: golden PRD case + manifest changes.log drift + real_embeddings model-skip"
swimlane: infra
kind: bug
epic: null
labels: [ci, release-unblock, case-sensitivity, manifest, embeddings, ready]
status: testing
priority: P0
appetite: 1d
created: 2026-06-22
started: 2026-06-22
completed: null
agent_session: ses-claude-20260621-232203-5c3d
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
