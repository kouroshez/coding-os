# Contributing to coding-os

Thank you for your interest in coding-os. This document is the
single source of truth for how to contribute code, docs, hooks,
adapters, or templates to the project.

> **Three-second summary:** fork → branch from `main` → conventional
> commit → run `make verify` → open a PR against `main`.

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Ways to Contribute](#ways-to-contribute)
3. [Development Setup](#development-setup)
4. [The Contribution Loop](#the-contribution-loop)
5. [Commit Message Style](#commit-message-style)
6. [Pull Request Checklist](#pull-request-checklist)
7. [Project Conventions](#project-conventions)
8. [Where Things Live](#where-things-live)
9. [Reviewing Other PRs](#reviewing-other-prs)
10. [Release Process](#release-process)

---

## Code of Conduct

This project follows the [Contributor Covenant 2.1](./CODE_OF_CONDUCT.md).
By participating you agree to uphold it. Report unacceptable behavior
to `conduct@coding-os.dev`.

## Ways to Contribute

| You want to…                       | Start here                                      |
| ---------------------------------- | ----------------------------------------------- |
| Report a bug                       | [Bug report template](.github/ISSUE_TEMPLATE/bug.yml) |
| Request a feature                  | [Feature request template](.github/ISSUE_TEMPLATE/feature.yml) |
| Report a security vulnerability    | [SECURITY.md](./SECURITY.md) (privately, please) |
| Improve docs                       | Edit any file under `docs/` and open a PR       |
| Add a stack template               | See `docs/playbooks/template-authoring.md`      |
| Add an agent adapter               | See `docs/playbooks/adapter-authoring.md`       |
| Add a hook                         | See `docs/playbooks/hook-authoring.md`          |
| Add an MCP tool                    | See `docs/playbooks/mcp-tool-authoring.md`      |
| Just say hello / ask a question    | Open a [Discussion](https://github.com/kouroshebra/coding-os/discussions) |

## Development Setup

Requirements:

- Python ≥ 3.10 (we test against 3.10, 3.11, 3.12).
- [uv](https://docs.astral.sh/uv/) (recommended) or pip.
- Node.js ≥ 20 (only if you touch `src/core/web/ui/`).
- Bash ≥ 4 (macOS ships with bash 3.2 by default; install via `brew install bash`).

Three adapters are wired today: `claude`, `codex`, `cursor` (under
`src/adapters/<id>/`). Each has its own `install.sh`; `cos init`
runs the right one based on `--agent`. All three speak the same MCP
server defined in `.mcp.json`.

### Option A — native install (recommended for daily work)

```bash
git clone https://github.com/kouroshebra/coding-os.git
cd coding-os
uv tool install --editable .          # installs the `cos` CLI globally
uv sync --extra rag                   # installs Python deps incl. semantic search
make dogfood                          # wire THIS repo's own .claude/ (hooks + MCP + slash commands)
cd src/core/web/ui && npm install     # optional, only for Hub UI work
```

> **Why `make dogfood`?** coding-os is itself a coding-os project (P5
> Dogfood). Its `.claude/` — hooks, MCP wiring, slash commands — is
> **generated** from `src/` and is **gitignored**, so a fresh clone has
> none. `make dogfood` renders the Claude adapter; `make dogfood-full`
> renders every adapter (`.claude/` + `.codex/` + `.cursor/`). Re-run it
> after any change under `src/core/**` or `src/adapters/**`. (Editing a
> hook *body* in `src/core/hooks/` takes effect immediately — `.claude/`
> symlinks into it — but registry/template changes need a re-render.)

Smoke test:

```bash
cos --version                         # should print cos 0.3.0
cos doctor                            # should report no critical issues
uv run --extra rag pytest src/core/thinking_os/tests/ -q   # ~3 min, full thinking_os suite
```

### Option B — Docker (zero local Python/Node)

The repo ships a production-shaped `Dockerfile` + `docker-compose.yml`
that bake the Hub into a single non-root container on port 9188.

```bash
git clone https://github.com/kouroshebra/coding-os.git
cd coding-os
docker compose up                     # → http://127.0.0.1:9188
```

Hub state (SQLite DB, traces) persists in the `cos-state` named
volume across `docker compose down` / `up`. Note: the image runs
only the Hub demo — `cos init` and the adapter wire-up still need
the native path above. Use Docker when you want to inspect the UI
without installing Python locally.

## The Contribution Loop

We use a five-phase loop adapted from John Boyd's OODA: **Classify →
Orient → Plan → Execute → Verify** (see `src/core/rules/thinking_os.md`).

Practically:

1. **Find or create an issue.** Don't open a large PR without a
   matching issue — it's easier to align on scope upfront.
2. **Branch.** Naming: `<kind>/<short-slug>` — e.g. `feat/add-redis-template`,
   `fix/hook-deadlock`. Branch from `main`.
3. **Make focused changes.** One PR = one concern. Refactors get
   their own PR even if they touch the same area.
4. **Run the matrix-targeted test for what changed.** See
   `src/core/rules/test-discipline.md` for the table; e.g.:
   - touched `src/core/thinking_os/**` → `uv run --extra rag pytest src/core/thinking_os/tests/ -q`
   - touched `src/core/hooks/*.sh` → `make verify-hooks`
   - touched `src/templates/**/scaffold/**` → `uv run pytest tests/test_template_scaffold.py -q`
5. **Update docs.** If you changed behavior, the doc for that behavior
   must change in the same PR.
6. **Open a PR** against `main`. CI will run the same matrix on
   every push.
7. **Iterate on review.** Squash-merge is the default when PRs land.

**Tooling shortcut:** inside an agent session the loop is driven by
**slash commands** — `/classify`, `/board`, `/task`, `/verify`, `/review`,
`/role-*`, etc. They are packaged workflows shipped in `.claude/commands/`
(and `.codex/commands/`). The full list and day-to-day usage are in
[docs/workflow/workflow-guide.md](docs/workflow/workflow-guide.md); the
sources live in [src/core/commands/](src/core/commands/).

## Commit Message Style

We use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/)
with project-specific scopes. Format:

```
<type>(<scope>): <subject>

<body — optional, wrap at 72 chars>

<footer — optional: BREAKING CHANGE, Refs #issue, etc.>
```

Allowed `<type>`:

| Type      | Use for                                       |
| --------- | --------------------------------------------- |
| `feat`    | New user-visible feature                      |
| `fix`     | Bug fix                                       |
| `perf`    | Performance improvement                       |
| `refactor`| Code reorganization with no behavior change   |
| `docs`    | Documentation only                            |
| `test`    | Test-only changes                             |
| `chore`   | Tooling, dependencies, repo housekeeping      |
| `ci`      | CI / GitHub Actions only                      |
| `style`   | Formatting, lint fixes (no semantic change)   |
| `build`   | Build system, pyproject, package.json         |

Suggested `<scope>` for this repo:

`hooks` · `mcp` · `graph` · `board` · `web` · `hub-ui` · `cli` ·
`adapters` · `templates` · `tests` · `docs` · `community` · `repo`

Subject line:

- ≤ 72 characters.
- Imperative mood (`add`, not `added` or `adds`).
- No period at the end.
- Start with lowercase letter.

Body (when needed):

- Explain **why**, not what — the diff already shows what.
- Reference issues (`Refs #42`, `Closes #42`) at the end.
- For BREAKING changes, include `BREAKING CHANGE:` paragraph with
  migration notes.

Good examples (drawn from the actual history):

```
fix(hooks): pre-commit deadlock — extract python heredoc per Rule 8
feat(intent): completion guardian + Stop hook (G4)
perf(web): gzip every /api response over 500 bytes (270KB → 21KB)
docs(adapter-parity): note intent enforcement is Claude/Cursor only
```

## Pull Request Checklist

Before requesting review, confirm:

- [ ] Branch is up to date with `main` (`git rebase main` or merge).
- [ ] Conventional Commit subject + body explain **why**.
- [ ] Matrix-targeted tests pass locally.
- [ ] `make verify-hooks` passes if you touched `src/core/hooks/`.
- [ ] `make docs-lint` passes if you touched `docs/**/*.md`.
- [ ] CHANGELOG entry added under `## [Unreleased]` for user-visible changes.
- [ ] New public symbol → has at least the one-line docstring required
      by Rule 12.
- [ ] New MCP tool → wrapped with `@safe_tool` returning `ok/fail`
      envelope per Rule 13.
- [ ] New hook → registered in `src/core/hooks/registry.yaml` + adapter
      templates regenerated (`make regen-adapter-templates`).
- [ ] No secrets, no absolute developer paths (`/Users/<name>`), no
      client-specific identifiers.
- [ ] PR description explains the **change**, the **motivation**, and
      the **test plan**.

## Project Conventions

The bedrock conventions, enforced by hooks where possible:

- **Rule 0 — Docs-first.** Every code Write/Edit traces to a documented
  spec via `.doc-anchor`. If the spec doesn't exist, write it first.
- **Rule 13 — MCP envelope.** Every `cos_*` returns `ok(data)` / `fail(category, message)`.
- **Rule 19 — Docs are the contract.** Never extend code beyond the
  doc spec; if a feature needs to grow, update the doc first.
- **Rule 22 — Anti-overengineering.** Reuse > duplicate. No speculative
  abstractions. Three similar lines is better than a premature abstraction.

The complete numbered list with rationale lives in
`docs/governance/critical-rules.md`.

## Where Things Live

```
src/core/      → DNA: agent-agnostic kernel (hooks, MCP, rules, skills)
src/adapters/  → mRNA: per-agent translation (claude, codex, cursor)
src/templates/ → phenotype: per-stack overlay (django, nextjs, ...)
src/cli/       → the `cos` factory CLI
src/scripts/   → maintenance tooling
docs/          → governance, engineering, playbooks, architecture
tests/         → cross-cutting tests (per-subsystem tests live next to the code)
```

Architecture overview: `docs/architecture/meta-project.md`.

## Reviewing Other PRs

If you're reviewing:

- Pull the branch and run it. Don't review by diff alone for non-trivial
  changes.
- Check whether the PR matches its claimed scope (no surprise refactors).
- Verify tests genuinely exercise the change (snapshot tests of the
  output, not just "it didn't crash").
- For docs PRs: read the rendered markdown, not just the source.
- Approvals require at least one maintainer or two trusted reviewers.

## Release Process

Releases are cut via [release-please](https://github.com/google-github-actions/release-please-action),
which reads Conventional Commits and prepares a CHANGELOG + version
bump PR automatically. Maintainer's only manual step is to merge that
PR; tagging + GitHub release + PyPI publish happen via the
`.github/workflows/release.yml` workflow.

If you need a fix released sooner than the next scheduled minor, ping
a maintainer on the PR or the corresponding issue.

---

Thank you for contributing. Every contribution — code, docs, bug
report, even a typo fix — helps this project be useful to the next
person who arrives.
