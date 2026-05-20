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
   <https://github.com/kouroshebra/coding-os/security/advisories/new>.
   This stays private until coordinated disclosure.
2. **Email:** `security@coding-os.dev` (PGP key fingerprint published
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
- Issues that depend on a CLI agent (Claude Code, Codex, Cursor)
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

## Hall of Fame

Researchers who report valid vulnerabilities and follow this policy
will be credited (with their permission) in the security advisory and
in the project CHANGELOG.
