<!-- domain:OPS | layer:policy | ssot:true | updated:2026-06-07 -->
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

### `uv.lock` rides along in the release PR

`release-type: python` bumps `pyproject.toml` but knows nothing about
`uv.lock`, which carries the project's own version too
([release-please#2561](https://github.com/googleapis/release-please/issues/2561),
open). Left alone the two diverge on every release — they did from 0.3.12
to 0.3.14 — and nobody notices, because a bare `uv sync` **silently
rewrites a stale lock and exits 0**. The repair is two halves that only
work together:

- **The bump** — an `extra-files` entry with a `toml` updater
  (`$.package[?(@.name.value=='coding-os')].version`) so the lock is
  bumped *inside* the release PR, not by a follow-up bot commit. Verified
  byte-identical to what `uv lock` writes.
- **The gate** — `uv lock --check` in the CI Lint job, **positioned above
  every `uv sync`** for the reason above. A jsonpath that stops matching
  no-ops with only a log line, so without this step the bump could
  silently stop working exactly as the original drift did.

Adding a dependency still means running `uv lock` and committing the
result, same as before.

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
5. **Never hand-bump the version in `uv.lock`.** release-please owns it on
   a release; a dependency change owns it via `uv lock`. Run `uv lock
   --check` before pushing if unsure — CI runs the same command.

## Operational notes

- **PR-creation permission** must stay on:
  `gh api -X PUT /repos/<owner>/<repo>/actions/permissions/workflow -F can_approve_pull_request_reviews=true`.
  If release-please fails with *"GitHub Actions is not permitted to create
  or approve pull requests"*, this toggle is off.
- A `GITHUB_TOKEN`-created release PR does **not** trigger downstream CI.
  To CI-gate the release PR, add a `RELEASE_PLEASE_TOKEN` PAT — tracked in
  TASK-076.
- Publishing (PyPI via Trusted Publishing) **is wired** — a `publish-pypi` job
  in `release-please.yml` gated on `releases_created`. It stays dormant on every
  push and only fires once the repo is public and a release PR merges (TASK-077,
  complete).
- `0.x` carries **no stability guarantee** (semver). The 1.0.0 cut
  criteria — frozen `cos init` output + `cos_*` MCP signatures — are
  tracked in TASK-079.

## Publishing & package metadata (as-built — TASK-077/219)

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

**2. `pyproject.toml` `[project]` metadata** — COMPLETE (landed in TASK-077/219):
`authors`, `license = "Apache-2.0"` (SPDX) + `license-files`, `classifiers`,
`keywords`, and `[project.urls]` are all present, alongside `name` · `version` ·
`description` · `readme` · `requires-python` · `dependencies` ·
`[project.scripts]` (`cos = cli.main:cli`) · `build-system` (setuptools.build_meta)
· src-layout.

**3. Runtime data must ship as package-data** — the installed `cos` reads
non-Python data trees at runtime; a wheel that omits them degrades **silently**.
`[tool.setuptools.package-data].core` MUST include: `hooks/*.sh`,
`hooks/_helpers/*.py`, `hooks/registry.yaml`, `commands/**`, `skills/**`,
`rules/*.md`, `schemas/*.json`, `thinking_os/agents/**`,
`thinking_os/{presets,situations,roles}/*.yaml`, `board_os/*.yaml`. (TASK-219 +
the H1 follow-up added presets/situations/roles/registry — a wheel install
otherwise silently dropped them, breaking compose-chain + situations.)

**Gotcha (resolved):** SPDX `license = "Apache-2.0"` + `license-files` needs
`setuptools>=77`; build-system now pins `>=77`.

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
| 4 | Adapter contract frozen | `adapter.yaml` schema stable across claude / codex |
| 5 | Quality gates promoted to required | ruff / mypy / eslint flipped from advisory to hard-fail in CI; baseline cleared |
| 6 | Deprecation policy published | post-1.0 breaks follow deprecate → warn → remove over ≥2 minors — [stability-contract.md](stability-contract.md) |

When all six hold, bump to `1.0.0` (a `feat!:` commit, or merge the release PR
after a manual manifest bump). Until then stay on `0.x` and flag every breaking
change with `!` so `^0.x` pinners are never surprised.

## See also

- [src/core/rules/git-workflow.md](../../src/core/rules/git-workflow.md) — commit-message contract + trunk discipline.
- [docs/governance/critical-rules.md](critical-rules.md) — Rule 23/24 (git workflow + commit message).
