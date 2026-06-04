---
id: TASK-085
title: "release: complete pyproject.toml package metadata for a professional PyPI page (pre-public-launch)"
swimlane: infra
kind: chore
epic: null
labels: []
status: archive
priority: P2
appetite: "1d"
created: 2026-06-04
started: null
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-085: release: complete pyproject.toml package metadata for a professional PyPI page (pre-public-launch)

**Outcome (one sentence):** Fill the missing [project] metadata in pyproject.toml so the PyPI listing is complete/professional before the first PUBLIC release. Do NOT do now — repo is still private; metadata edit is safe but pointless until publish. Sequence: do this in the same batch as TASK-077 (publish job), right before the first public release.

MISSING fields to add (per official tutorial https://packaging.python.org/en/latest/tutorials/packaging-projects/):
- authors = [{name="Kourosh ...", email="..."}]
- license — SPDX expression matching the existing LICENSE file (11K, detect its type) + license-files = ["LICENSE"]
- classifiers — Programming Language :: Python :: 3.10/3.11/3.12, License :: ..., Operating System :: OS Independent, Development Status :: 4 - Beta (0.x), Intended Audience :: Developers
- keywords — ai, coding-agent, mcp, llm, cli, hexagonal, claude, codex
- [project.urls] — Homepage / Repository / Issues → https://github.com/kouroshez/coding-os

ALREADY publish-ready (do not touch): name=coding-os, version, description, readme, requires-python>=3.10, dependencies, [project.scripts] cos=cli.main:cli, build-system=setuptools.build_meta, src-layout.

GOTCHA: modern SPDX `license="MIT"` + license-files needs setuptools>=77 (current build-system pins >=68) — either bump to >=77 OR use legacy `license={file="LICENSE"}`. Pick one.

VERIFY: `uv build` produces a clean wheel+sdist; inspect rendered metadata (twine check dist/*); optionally dry-run on TestPyPI before real PyPI. Companion: TASK-077 (publish job) + TASK-079 (1.0.0 criteria).

## Work Log
