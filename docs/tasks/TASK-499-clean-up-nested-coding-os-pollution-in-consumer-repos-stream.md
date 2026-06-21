---
id: TASK-499
title: "Clean up nested .coding-os pollution in consumer repos (streamos, cos-website): git rm tracked stray + delete on-disk src/** strays"
swimlane: core
kind: chore
epic: null
labels: [cleanup, consumer-repo, hygiene, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-21
started: null
completed: null
agent_session: null
depends_on: [TASK-490]
blocked_by: []
references: []
---

# TASK-499: Clean up nested .coding-os pollution in consumer repos (streamos, cos-website): git rm tracked stray + delete on-disk src/** strays

**Outcome (one sentence):** All nested (non-root) .coding-os pollution left by the pre-fix bug is removed from registered consumer projects: the git-TRACKED stray runtime file in streamos (src/backend/.coding-os/claude/panels/.../heartbeat) is removed from the index via git rm --cached, and untracked on-disk nested .coding-os/ dirs under src/** in streamos and cos-website are deleted. Each project's ROOT .coding-os/ (with its tracked config files) is preserved untouched. Runs AFTER TASK-490 lands so the strays cannot regrow.

## Work Log
