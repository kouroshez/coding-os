<!-- domain:ALL | layer:reference | ssot:true | updated:{{DATE}} -->
# `src/shared/` — Cross-Stack Contract Layer

Purpose: Hosts types, contracts, and constants that two or more stacks must agree on. The only directory every installed stack is allowed to import from (per each stack's `scaffold-boundary.yaml::imports_from`).

Read when: Adding a field that crosses a stack boundary (e.g. backend response shape consumed by frontend or mobile).

Skip when: The artifact lives entirely inside one stack — keep it there.

## Layout

```
src/shared/
├── types/         # language-neutral type declarations (e.g. TypeScript .d.ts, Pydantic JSON schemas, .proto)
└── contracts/     # API / event / message contracts that pin producer ↔ consumer
```

## Rules

- Producers (backend / api / worker) MUST update `src/shared/` BEFORE consumers (frontend / mobile) read the new shape.
- No stack writes into another stack's root — cross-stack changes flow through `src/shared/` only.
- See [governance/scaffold-boundary-contract.md](../../docs/governance/scaffold-boundary-contract.md) for the per-stack boundary that pins the policy.
- See [engineering/api-contract-discipline.md](../../docs/engineering/api-contract-discipline.md) (if installed) for why consumers verify field names against producers, not memory.
