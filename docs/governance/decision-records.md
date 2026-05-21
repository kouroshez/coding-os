<!-- domain:DOCS | layer:reference | ssot:true | updated:{{DATE}} -->
# Decision Records

Purpose: Define where durable architectural decisions live and how to reference them from tasks and governance docs.
Read when: A change introduces or depends on a long-lived technical decision.
Skip when: The task only needs an already-linked ADR and no decision-model update is required.
Read next: `../architecture/adr/00-index.md`

> Nav: [Docs Index](../00-index.md) | [ADR Index](../adr/0000-index.md)

## Rules

- Stable architectural decisions belong in ADR files under `docs/architecture/adr/`.
- Governance docs may summarize decisions, but ADR files are canonical.
- Historical migration decisions that are no longer active belong in governance archive docs, not evergreen architecture pages.

## When to Create an ADR

- Provider choice with long-lived impact (e.g. payment provider, mail service)
- Security model change
- Infra/runtime tradeoff with operational consequences
- Schema or API strategy that future work must inherit
- Library or framework version pin with migration cost

## ADR Template

Each ADR follows this structure:

```markdown
<!-- domain:XXX | layer:adr | ssot:true | updated:YYYY-MM-DD -->
# ADR-NNN: Short Decision Title

> Nav: [ADR Index](./00-index.md)

## Status

Proposed | Accepted | Deprecated | Superseded by ADR-XXX

## Context

What is the issue we're seeing that motivates this decision?

## Decision

What is the change we're actually proposing or doing?

## Consequences

What becomes easier or harder as a result of this change?

## Alternatives Considered

Which alternatives were considered and why were they rejected?
```

## Numbering

ADRs use sequential 3-digit numbering: `ADR-001-...md`, `ADR-002-...md`, etc. Numbers are never reused, even when an ADR is superseded.
