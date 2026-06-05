---
id: TASK-106
title: "Clean drift surfaced by output-quality gates: nako_/.claude refs, codex dispatcher drift, scaffold_manifest staleness, malformed frontmatter"
swimlane: infra
kind: chore
epic: null
labels: [tech-debt, drift, golden, follow-up-TASK-100]
status: icebox
priority: P2
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-106: Clean drift surfaced by output-quality gates: nako_/.claude refs, codex dispatcher drift, scaffold_manifest staleness, malformed frontmatter

**Outcome (one sentence):** The drift that TASK-100's honest gates exposed is cleaned: make audit green (0 nako_/.claude), verify-dispatchers wired + codex dispatcher synced, scaffold_manifest regenerated (doctor manifest_fresh=PASS), malformed frontmatter fixed. Includes Batch 7 dead-stub removal (verify-changed-file.sh + doc-sync-reminder.sh) which needs a clean no-concurrent-session window for golden-capture.

## Work Log
