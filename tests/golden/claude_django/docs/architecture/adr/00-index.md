<!-- domain:ARCH | layer:index | ssot:true | updated:2026-01-01 -->
# Architecture Decision Records — Index

Purpose: Index of all immutable architecture decisions.
Read when: Considering a change that touches a previously-decided area, or onboarding to architectural choices.
Skip when: The active task is in a domain with no relevant ADR.
Read next: The specific ADR file referenced from your task.

> Nav: [Architecture Index](../00-index.md) | [Docs Index](../../00-index.md)

## ADRs

<!-- Add ADRs in chronological order. Format:
- [ADR-001](./ADR-001-short-title.md) — One-line summary
-->

(empty — populate as decisions are recorded)

## Process

1. When a long-lived architectural decision is needed, create `ADR-NNN-kebab-title.md`.
2. Number sequentially. Never reuse numbers, even when an ADR is superseded.
3. Use the template in `../../governance/decision-records.md` § ADR Template.
4. Status starts as `Proposed`, moves to `Accepted` after implementation, or `Superseded by ADR-XXX` when replaced.
5. Add the new ADR to the list above.
6. Reference the ADR ID from related task files and architecture docs.

## When to Create an ADR

See `../../governance/decision-records.md` § When to Create an ADR.

Common triggers:

- Provider choice (payment, email, hosting, search)
- Library/framework version pin with migration cost
- Security model change
- Data store choice
- API contract strategy
- Build/deploy strategy
