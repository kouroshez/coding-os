---
id: TASK-895
title: "Restore green CI on main and clear the Dependabot PR backlog after the repo rebuild"
swimlane: infra
kind: chore
epic: null
labels: [ci, release, dependencies]
status: "in_progress"
priority: P1
appetite: 1d
created: 2026-08-06
started: 2026-08-06
completed: null
agent_session: ses-claude-20260803-180632-5fca
depends_on: []
blocked_by: []
references: []
---

# TASK-895: Restore green CI on main and clear the Dependabot PR backlog after the repo rebuild

**Outcome (one sentence):** main is green, 0.3.5 is on PyPI, and the 3 open Dependabot PRs are merged or closed with a stated reason.

## Work Log
- 2026-08-06 [claude]: commit 4251243bb2 — fix(ci): refresh golden fixtures and scaffold manifest for the CLAUDE.md entrypoint
- 2026-08-06 [claude]: commit 2903f7b91d — ci: move the frontend jobs and UI build image off end-of-life Node 20
- 2026-08-06 [claude]: commit 5927792173 — chore(board): bind TASK-895 to the active session
- 2026-08-06 [claude]: Published coding-os 0.3.5 to PyPI directly (wheel+sdist) after the Actions outage blocked the OIDC job three times;…
- 2026-08-06 [claude]: commit 234fd5fb7c — chore(board): record the PyPI publish and CI-repair work log on TASK-895
- 2026-08-06 [claude]: commit b5db7e8cc3 — chore(deps): bump jsdom from 29.1.1 to 30.0.1 in /src/core/web/ui
- 2026-08-06 [claude]: Closed out the PR backlog: 0 open PRs, only main remains. #15 could not be rebased because GitHub throttled webhooks…
- 2026-08-06 [claude]: commit 68d9e8490a — chore(board): log the PR-backlog closeout on TASK-895
- 2026-08-06 [claude]: Edit release-please.yml
- 2026-08-06 [claude]: Edit release-please.yml
- 2026-08-06 [claude]: Edit renderer.py
- 2026-08-06 [claude]: Edit renderer.py
- 2026-08-06 [claude]: commit cceba34500 — fix(cli): emit Node 22 in generated CI and the TypeScript Dockerfile
- 2026-08-06 [claude]: commit ce2d180a0d — fix(release): keep the PyPI recovery hatch reachable and pin checkout to the release sha
