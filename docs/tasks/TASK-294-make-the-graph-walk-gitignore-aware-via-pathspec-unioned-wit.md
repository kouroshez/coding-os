---
id: TASK-294
title: "Make the graph walk .gitignore-aware via pathspec, unioned with the static denylist"
swimlane: core
kind: feature
epic: graph-coverage-hardening
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-09
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260608-203030-6c0f
depends_on: []
blocked_by: []
references: []
---
# TASK-294: Make the graph walk .gitignore-aware via pathspec, unioned with the static denylist

**Outcome (one sentence):** DEFAULT_EXCLUDE is a static ~22-name denylist and the walk is not .gitignore-aware, so custom build/output dirs (out/ bin/ obj/ coverage/ .tox/ htmlcov/ __snapshots__/) pollute the graph; parse .gitignore (+ nested + .git/info/exclude) via pathspec and union with the denylist so exclusion matches exactly what git ignores.

## Read First
- src/core/graph_os/ingest/base.py
- docs/engineering/graph_os-queries.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a repo whose .gitignore lists a dir NOT in DEFAULT_EXCLUDE (e.g. out/), **When** the graph walk enumerates files, **Then** files under that dir are excluded just as git would ignore them.
- **Given** pathspec is not installed, **When** the walk runs, **Then** it falls back cleanly to the static denylist (fail-open, no crash) — the .gitignore layer is additive, never required.
- **Then** the static denylist remains a backstop (still excludes node_modules/.venv even if absent from .gitignore), nested .gitignore files are honored, and a graph_os test proves a .gitignore-only dir is skipped; matrix command green.

## Work Log
- 2026-06-09 [claude]: walk_local now unions DEFAULT_EXCLUDE with .gitignore (root + nested + .git/info/exclude) via pathspec GitIgnoreSpec; fa
- 2026-06-09 [claude]: committed 1f85abd6: docs/engineering/graph_os-queries.md, pyproject.toml, src/core/graph_os/ingest/base.py, src/core/gra
