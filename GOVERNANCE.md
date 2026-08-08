# Governance

How decisions get made in coding-os. Honest for the project's current
stage: one maintainer, agent-assisted development, trunk-based flow. The
document exists so that the *process* survives the person — a newcomer
should be able to predict how any change lands without asking.

## Decision model — solo maintainer (BDFL-style)

- **Final say:** the maintainer listed in [MAINTAINERS.md](MAINTAINERS.md)
  decides on scope, design, and releases.
- **How to influence a decision:** open a GitHub issue (bugs/features) or
  a Discussion (design questions). Decisions with lasting consequences are
  recorded as ADRs under `docs/architecture/adr/`.
- **Values the decisions derive from:**
  [docs/governance/constitution.md](docs/governance/constitution.md) — the
  eight values every rule in this repo traces back to.

## How changes land

- **Trunk-based:** commits go directly to `main`
  ([critical-rules.md § Rule 23](docs/governance/critical-rules.md#rule-23--trunk-based-git-workflow)).
  External contributors work via fork + pull request.
- **Quality gates are the reviewer of record:** every push runs the
  blocking `CI Pass` check — ruff (zero findings, incl. complexity
  gates), format, the mypy count-ratchet, shellcheck, the full test
  matrix, the coverage gate (`fail_under` in `pyproject.toml`), the
  file-size ratchet, docs-lint, CodeQL, and (on PRs) dependency-review +
  diff-cover ≥80% on changed lines. Branch protection on `main` requires
  `CI Pass` and linear history. Gate detail + ratchet protocol:
  [docs/engineering/ci-gates.md](docs/engineering/ci-gates.md).
- **External PRs** additionally get a human maintainer review before
  merge; the merge queue serializes them against `main`.

## Releases

Automated by release-please: Conventional-Commit titles drive the
version and `CHANGELOG.md`; publishing to PyPI uses Trusted Publishing
(OIDC). Nobody hand-edits the changelog or tags. Spec:
[docs/governance/release-process.md](docs/governance/release-process.md)
— including the six criteria that gate the 1.0 bump.

## Becoming a maintainer

A contributor with a sustained record (several merged PRs across more
than one subsystem, sound review judgment, adherence to the constitution)
can be nominated in a Discussion by any existing maintainer and is added
on the current maintainers' agreement. Maintainers inactive for 12
months move to emeritus (listed, no merge rights).

## Security

Report vulnerabilities per [SECURITY.md](SECURITY.md) — privately, not
via public issues.
