---
id: TASK-077
title: "release: wire publish job (PyPI / uvx / GHCR) gated on releases_created once distribution channel is decided"
swimlane: infra
kind: chore
epic: null
labels: []
status: icebox
priority: P2
appetite: "1d"
created: 2026-06-04
started: 2026-06-04
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-077: release: wire publish job (PyPI / uvx / GHCR) gated on releases_created once distribution channel is decided

**Outcome (one sentence):** Make coding-os publicly installable (`pip` / `pipx` / `uvx install coding-os`) before the first public release — wire a PyPI publish job (Trusted Publishing, gated on `releases_created`) AND complete `pyproject.toml` metadata (authors · license · classifiers · keywords · urls). **Full spec:** [docs/governance/release-process.md § Publishing & package metadata](../governance/release-process.md#publishing--package-metadata-pre-public-launch--task-077). Deferred — repo still private; do at public-launch alongside the first release tag (companion of TASK-079 1.0.0 criteria).

## Work Log
