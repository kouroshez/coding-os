---
id: TASK-891
title: "Pre-purge history survives in GitHub pull-request refs \u2014 third-party material still publicly fetchable"
swimlane: infra
kind: security
epic: null
labels: [ready]
status: complete
priority: P0
appetite: 1d
created: 2026-08-05
started: 2026-08-05
completed: 2026-08-09
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-891: Pre-purge history survives in GitHub pull-request refs — third-party material still publicly fetchable


**Outcome (one sentence):** No third-party copyrighted file is retrievable from any ref of the public repository, including the read-only `refs/pull/*` refs that a force-push cannot rewrite.

## Read First
- `docs/tasks/TASK-877-*` — the original purge task, whose verification only covered `main`
- GitHub docs, "Removing sensitive data from a repository" — the post-rewrite Support step
- The earlier force-push transcript: `refs/pull/*` rejections were observed and wrongly dismissed as benign

## Threat Model
- **Attacker:** any anonymous visitor; no account, token or prior knowledge of object ids required.
- **Asset:** the maintainer's professional standing and the project's licensing posture — the material is third-party copyrighted work (an academic dissertation, a vendor certification guide, a television screengrab).
- **Vector:** the history rewrite replaced `refs/heads/main` but GitHub's `refs/pull/*` refs are server-owned and immutable to the repository owner. They pin the pre-purge commits, so the objects stay reachable — and therefore survive any garbage collection — and are enumerable through the public tree API and fetchable through `raw.githubusercontent.com`.
- **Mitigation:** only GitHub Support can drop `refs/pull/*` and run the collection; alternatively the repository can be recreated. Both are operator actions, not agent actions.
- **Residual risk:** anything already cloned or cached by a third party is beyond recall; the exposure window began at public launch.

## Repro Steps
1. `git ls-remote` the public repository and fetch `+refs/pull/*/head:refs/remotes/pr/*`.
2. Test ancestry of the pre-purge root commit against each fetched ref — 14 of 47 still contain it.
3. Read the tree of any such ref: the files removed by the purge are listed with their sizes, and `raw.githubusercontent.com` serves them at HTTP 200 without authentication.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the public repository and no credentials,
- **When** every remote ref is enumerated and its tree walked,
- **Then** no path under the third-party documentation directory resolves, and the previously reachable blobs return 404.

## Work Log
- 2026-08-05 [claude]: Reproduced unauthenticated, from outside: the pre-purge root commit is not an ancestor of main, but it IS an ancestor…
- 2026-08-09 [claude]: Verified closed: repo recreated 2026-08-06T02:53:57Z (API created_at), forks=0 network=0, all 4 pre-purge SHAs return…
- 2026-08-09 [claude]: Retained-files audit: 6 .md remain under docs/code-os-core-docs/ but all carry this project's own SSOT headers…
- 2026-08-09 [claude]: Status transitioned to complete via cos task-done.
- 2026-08-09 [claude]: Edit test_hooks_phase_f.py
- 2026-08-09 [claude]: Edit update.py
- 2026-08-09 [claude]: Edit update.py
- 2026-08-09 [claude]: Edit update.py
- 2026-08-09 [claude]: Edit ci.yml
- 2026-08-09 [claude]: Edit ci-gates.md
- 2026-08-09 [claude]: Edit test_frontmatter_repair.py
- 2026-08-09 [claude]: Edit mypy_ratchet.py
- 2026-08-09 [claude]: Edit ci-gates.md
- 2026-08-09 [claude]: commit a11ebb31e4 — ci: re-measure the mypy baseline from CI and make a rise diagnosable
- 2026-08-09 [claude]: commit 8bd7c6862c — chore(board): sync TASK-891 work log
- 2026-08-09 [claude]: Edit release-please.yml
- 2026-08-09 [claude]: Edit release-please.yml
- 2026-08-09 [claude]: commit 652744fece — fix(ci): write the release SBOM to an existing directory
- 2026-08-09 [claude]: Edit release-please.yml
