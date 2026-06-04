# Release Process (SSOT)

> **Model:** Releases are **data-driven** — Conventional Commits decide the
> version, [release-please](https://github.com/googleapis/release-please)
> computes it, a human merges one PR. **Nobody — human or agent — picks a
> version number, edits `CHANGELOG.md`, or creates a tag by hand.** That is
> the entire anti-foot-gun contract.

## Why this exists

656+ commits sat with zero releases because the automation that was
*already configured* (`release-please.yml`) silently failed on a repo
setting (`Allow GitHub Actions to create and approve pull requests` was
off). The fix was one toggle — not a new system. This doc records the
model so neither the maintainer nor an AI agent re-breaks it.

## The pipeline (one standing PR)

```
commit (Conventional) → push main → release-please reads commits
   → maintains ONE standing "release" PR (bumps version + CHANGELOG)
   → human merges the PR → tag + GitHub Release cut
```

- Config: [release-please-config.json](../../release-please-config.json) (`release-type: python`, package `coding-os`).
- Version cursor: [.release-please-manifest.json](../../.release-please-manifest.json).
- Workflow: [.github/workflows/release-please.yml](../../.github/workflows/release-please.yml).

## Roles — minimal decision surface

| Actor | Only job | Must NOT |
|---|---|---|
| **Agent** | Write a **valid Conventional Commit** message | pick a version · edit CHANGELOG · `git tag` |
| **Maintainer** | **Merge** the standing release PR when ready to cut | hand-edit version / CHANGELOG / tag |
| **release-please** | Derive semver, write CHANGELOG, open/refresh the PR | — |

Anti-hallucination by construction: the agent never names a version, so
it cannot name a *wrong* one. The commit log **is** the source of truth.

## Conventional Commit → version bump (pre-1.0)

| Prefix | Section | Bump (`bump-minor-pre-major`) |
|---|---|---|
| `feat:` | Added | minor (0.x.0) |
| `fix:` / `perf:` | Fixed / Performance | patch (0.0.x) |
| `feat!:` / `BREAKING CHANGE:` | — | minor pre-1.0 (would be major post-1.0) |
| `docs:` `build:` | Documentation / Build | patch |
| `ci:` `test:` `chore:` `style:` `refactor:` | hidden / Changed | no release on its own |

The commit **title type prefix is validated** by
[check_commit_message.py](../../src/core/hooks/_helpers/check_commit_message.py)
(Conventional grammar `type(scope)?!: subject`). A commit release-please
cannot parse is blocked before it lands — closing the gap where a
malformed type silently dropped a change from the changelog.

## Hard rules (enforced + by-convention)

1. **Never hand-edit `CHANGELOG.md`.** release-please owns it; a manual
   edit collides with the standing PR and rots it. Add a `feat`/`fix`
   commit instead.
2. **Never `git tag` a release by hand.** Merging the release PR is the
   only way a tag is created.
3. **Never force-push to rewrite a released tag.** Use `git revert`.
4. **Breaking change = `!` / `BREAKING CHANGE:`.** A break is anything in
   AGENTS.md § Stop Conditions: `cos init` output shape change, an MCP
   tool signature change, or a hook contract change consumers depend on.

## Operational notes

- **PR-creation permission** must stay on:
  `gh api -X PUT /repos/<owner>/<repo>/actions/permissions/workflow -F can_approve_pull_request_reviews=true`.
  If release-please fails with *"GitHub Actions is not permitted to create
  or approve pull requests"*, this toggle is off.
- A `GITHUB_TOKEN`-created release PR does **not** trigger downstream CI.
  To CI-gate the release PR, add a `RELEASE_PLEASE_TOKEN` PAT — tracked in
  TASK-076.
- Publishing (PyPI / `uvx` / GHCR) is **intentionally not wired** — add a
  `release` job gated on `releases_created` once a channel is chosen
  (TASK-077).
- `0.x` carries **no stability guarantee** (semver). The 1.0.0 cut
  criteria — frozen `cos init` output + `cos_*` MCP signatures — are
  tracked in TASK-079.

## See also

- [src/core/rules/git-workflow.md](../../src/core/rules/git-workflow.md) — commit-message contract + trunk discipline.
- [docs/governance/critical-rules.md](critical-rules.md) — Rule 23/24 (git workflow + commit message).
