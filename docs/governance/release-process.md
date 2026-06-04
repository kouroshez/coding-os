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

## Publishing & package metadata (pre-public-launch — TASK-077)

Goal: make `cos` publicly installable —

```bash
pip install coding-os      # or: pipx install coding-os · uvx coding-os
```

All three resolve from **PyPI** — publish once, all three work. **Do NOT wire
this until the repo goes public:** publishing uploads the wheel publicly even
while the repo is private. Sequence it with the first public release.

**Channel:** PyPI (the Python-CLI standard). uvx-from-git is a fallback; GHCR
(container) is the wrong fit for a local dev tool.

### Two pieces, landed together

**1. Publish job** — a job in `release-please.yml` gated on `releases_created`,
using **Trusted Publishing** (OIDC, no token):
- `pypa/gh-action-pypi-publish` + `permissions: id-token: write`;
- register the repo as a trusted publisher on the PyPI project first;
- result: every merged release auto-publishes to PyPI.

**2. Complete `pyproject.toml` `[project]` metadata** — currently MISSING, needed
for a professional PyPI page (per the [official tutorial](https://packaging.python.org/en/latest/tutorials/packaging-projects/)):
- `authors` (name + email)
- `license` (SPDX, from the existing LICENSE) + `license-files = ["LICENSE"]`
- `classifiers` (Python 3.10–3.12 · License · OS Independent · Development Status :: 4 - Beta · Intended Audience :: Developers)
- `keywords` (ai · coding-agent · mcp · llm · cli · hexagonal · claude · codex)
- `[project.urls]` (Homepage / Repository / Issues → github.com/kouroshez/coding-os)

Already publish-ready (do not touch): `name` · `version` · `description` ·
`readme` · `requires-python` · `dependencies` · `[project.scripts]`
(`cos = cli.main:cli`) · `build-system` (setuptools.build_meta) · src-layout.

**Gotcha:** SPDX `license = "MIT"` + `license-files` needs `setuptools>=77`
(build-system pins `>=68`) — bump it, or use legacy `license = {file = "LICENSE"}`.

### Verify
`uv build` (clean wheel + sdist) · `twine check dist/*` · dry-run on **TestPyPI**
(`pip install -i https://test.pypi.org/simple/ coding-os`) before the real index.

## 1.0.0 cut criteria (TASK-079)

`0.x` gives consumers **no stability guarantee** (semver). Cut `1.0.0` only when
the contracts below are frozen — it is a set of gates, not a date. All must hold:

| # | Criterion | Signal it's met |
|---|---|---|
| 1 | `cos init` scaffold output shape frozen | `tests/golden/**` stable across ≥2 minors; no planned skeleton change |
| 2 | `cos_*` MCP tool signatures frozen | `cos_graph_contracts` / tool inventory stable; `ok`/`fail` envelope unchanged |
| 3 | Hook contract frozen | `$COS_*` env + `registry.yaml` shape stable; no consumer-visible hook renames |
| 4 | Adapter contract frozen | `adapter.yaml` schema stable across claude / codex / cursor |
| 5 | Quality gates promoted to required | ruff / mypy / eslint flipped from advisory to hard-fail in CI; baseline cleared |
| 6 | Deprecation policy published | post-1.0 breaks follow deprecate → warn → remove over ≥2 minors, documented here |

When all six hold, bump to `1.0.0` (a `feat!:` commit, or merge the release PR
after a manual manifest bump). Until then stay on `0.x` and flag every breaking
change with `!` so `^0.x` pinners are never surprised.

## See also

- [src/core/rules/git-workflow.md](../../src/core/rules/git-workflow.md) — commit-message contract + trunk discipline.
- [docs/governance/critical-rules.md](critical-rules.md) — Rule 23/24 (git workflow + commit message).
