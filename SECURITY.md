# Security Policy

## Supported Versions

The latest minor release receives security updates. Older minors receive
security patches only for critical (CVSS ≥ 9.0) vulnerabilities for 90
days after a new minor lands.

| Version | Supported          |
| ------- | ------------------ |
| 0.3.x   | :white_check_mark: |
| < 0.3   | :x:                |

## Reporting a Vulnerability

**Do not open public GitHub issues for security vulnerabilities.**

Instead, report them privately via one of these channels:

1. **GitHub Security Advisories (preferred):** open a draft advisory at
   <https://github.com/kouroshez/coding-os/security/advisories/new>.
   This stays private until coordinated disclosure.
2. **Email:** `info@coding-os.dev` (PGP key fingerprint published
   in the repository's `.well-known/security.txt` once available).

When reporting, please include:

- A description of the vulnerability and its potential impact.
- Step-by-step instructions to reproduce, including any required
  configuration, payloads, or environment.
- Affected versions / commit SHAs you tested against.
- Any proof-of-concept code, log snippets, or screenshots.
- Whether the vulnerability is already public (e.g., disclosed in
  another upstream).

## Response Targets

We aim for the following timelines, measured from the receipt of a
complete report:

| Stage                              | Target          |
| ---------------------------------- | --------------- |
| Initial acknowledgement            | within 3 days   |
| Triage + severity assessment       | within 7 days   |
| Fix prepared (critical)            | within 30 days  |
| Fix prepared (high)                | within 60 days  |
| Fix prepared (medium / low)        | next minor      |
| Public advisory after coordinated  | within 90 days  |
| disclosure                         |                 |

These are targets, not guarantees. Reports that involve a
chain-of-vulnerabilities or require upstream coordination may take
longer; we will communicate progress at least every 14 days.

## Scope

In scope:

- Source code in this repository under `src/`.
- Configuration files we ship (`pyproject.toml`, `Makefile`,
  `.github/workflows/`, hook scripts under `src/core/hooks/`).
- Documentation that asserts security guarantees.

Out of scope:

- Vulnerabilities in upstream dependencies — please report those to
  the upstream project. We will pin / patch once upstream lands a fix.
- Vulnerabilities that require an attacker with local shell access to
  the machine running coding-os (the threat model assumes the local
  user is trusted).
- Issues that depend on a CLI agent (Claude Code, Codex)
  ignoring its own guardrails — those belong to the agent's vendor.

## Hardening Guidance

When deploying coding-os in a multi-user or production environment:

- Run the MCP server under a dedicated unprivileged user.
- Set `COS_DB_PATH` to a directory the running user owns exclusively
  (default `.coding-os/coding-os.db` is per-project, single-user).
- Audit hook configuration in `src/core/hooks/registry.yaml` before
  installing on a new machine; hooks execute arbitrary shell.
- Do **not** commit `.env` files, API keys, or service-account JSON;
  the bundled `block-secrets.sh` hook is best-effort, not a guarantee.
- Use GitHub's dependency-graph + Dependabot (already configured in
  `.github/dependabot.yml`) to track CVEs in transitive deps.

## Test fixtures for secret detection

This repository ships a secret detector
([`src/core/hooks/block-secrets.sh`](src/core/hooks/block-secrets.sh)), and a
detector can only be trusted if something feeds it credential-shaped input. So a
small, enumerated set of files contains strings that *look* like AWS, GitHub,
Stripe, Anthropic or Slack credentials.

**None of them is a credential, and you should not have to take our word for it.**
Every fixture is unusable by construction, using one of three techniques:

| Technique | Why it is safe | Example |
| --- | --- | --- |
| **Composed at run time** | The literal never exists in the tree, so no scanner — ours, GitHub's, or yours — can match it | `"sk-ant-api03-" + "A1b2C3d4" * 11` in `tests/test_block_secrets.py` |
| **Deliberately sub-threshold** | The body is shorter than the vendor's real key length, so it is not a valid key shape | a Stripe-prefixed string with a 15-character body, where real keys carry 24 or 99 |
| **Vendor-published example** | The vendor reserves the value and it can never authenticate | AWS's documented access-key identifier ending in `EXAMPLE` |

If you are writing a new detector test, **use one of those three** — preferably
the first. Do not paste a realistic full-length value, even a made-up one: it
will fire GitHub secret scanning on every fork, and the next reader cannot tell
your invention from a real leak.

This is not an honour system:

- [`.github/secret_scanning.yml`](.github/secret_scanning.yml) declares the
  fixture paths to GitHub in the repository itself, so the reasoning is public
  and reviewable in a pull request rather than buried in an alert dismissal.
- `tests/test_secret_fixture_policy.py` fails the build if any tracked file
  gains a literal that would match a real vendor pattern at full length.
- `block-secrets.sh` and the git `pre-commit` hook scan **every** commit and do
  not honour `paths-ignore`, so the exclusion above narrows dashboard noise, not
  the actual guard.

**Found a credential-shaped string in this repo and want to be sure?** Check its
length against the vendor's published key format first — most of ours are
visibly short — then report it via the process above. A false positive reported
in good faith is always welcome; we would rather answer ten of those than miss
one real leak.

## Hall of Fame

Researchers who report valid vulnerabilities and follow this policy
will be credited (with their permission) in the security advisory and
in the project CHANGELOG.
