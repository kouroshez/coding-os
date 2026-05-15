<!-- domain:ARCH | layer:index | ssot:true | updated:{{DATE}} -->
# Architecture — Index

Purpose: Navigation hub for architecture documentation.
Read when: Starting a task that touches system design, infrastructure, or cross-cutting concerns.
Skip when: The task is isolated to a single module already covered by its playbook.
Read next: The relevant numbered architecture doc or ADR below.

> Nav: [Docs Index](../00-index.md) | [ADR Index](./adr/00-index.md)

## Suggested Structure

Architecture is split into focused files. Populate as the project grows. Recommended order:

- `01-executive-summary.md` — One-page system overview
- `02-tech-stack.md` — Languages, frameworks, libraries with version pins
- `03-project-structure.md` — Directory layout and module boundaries
- `04-security-guardrails.md` — Authn, authz, secrets, web security
- `05-testing-strategy.md` — Test pyramid, coverage targets, CI gates
- `06-deployment-infra.md` — Hosting, runtime, CI/CD, environments
- `07-observability.md` — Logging, metrics, tracing, alerts
- `08-data-architecture.md` — Database, caching, search, analytics
- `09-integrations.md` — External services and API dependencies

## Architecture Decision Records (ADRs)

ADRs capture immutable architectural decisions. See `./adr/00-index.md`.

## Format

Each architecture doc follows the standard header:

```html
<!-- domain:ARCH | layer:spec | ssot:true | updated:YYYY-MM-DD -->
```

## Authoring Rules

- Architecture docs describe **what is** (current state) and **why** (rationale).
- Aspirational architecture goes in `../_meta/roadmap.md` or a new ADR with `Status: Proposed`.
- When code diverges from architecture docs, update the docs in the same PR that changes the code.
- For new domains, follow the Extension Protocol in `../governance/docs-system.md`.
