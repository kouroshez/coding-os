---
id: TASK-456
title: "B-10: module-aware cos init --dry-run (INIT-4) + PR-gate scaffold-manifest freshness (INIT-1)"
swimlane: cli
kind: chore
epic: null
labels: [modularity-audit-pass3, INIT-1, INIT-4, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-19
started: 2026-06-19
completed: 2026-06-19
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-456: B-10: module-aware cos init --dry-run (INIT-4) + PR-gate scaffold-manifest freshness (INIT-1)

**Outcome (one sentence):** INIT-4: cos init --dry-run now threads --disable-module into _scaffold_tree_preview and applies the same _apply_doc_conditions whole-file module-tag skip the real overlay uses, so the preview matches the actual --disable-module init (latent today — no whole-file-tagged scaffold doc exists yet, so it is a no-op that prevents future preview/actual drift). INIT-1: confirmed the committed scaffold_manifest.json is FRESH (make manifest-regen produced a byte-identical file) and wired tests/test_manifest_fresh.py into a PR job so single-stack scaffold drift for the ~50 non-golden stacks is caught on the PR, not only nightly.

## Work Log
- 2026-06-19 [claude]: committed f43ce5a9 · 2 files
- 2026-06-19 [claude]: Edit ci.yml
- 2026-06-19 [claude]: committed cb457e7c · 1 file
