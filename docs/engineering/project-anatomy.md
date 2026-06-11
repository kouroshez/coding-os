<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-06-11 -->
# Project Anatomy — Polyglot Coexistence Contract

> SSOT for the top-level directory anatomy every consumer project follows,
> and for how multiple stacks coexist without breaking each other's tree.
> Per-stack inner trees live in each `stack.yaml::structure`. TASK-351.

## The top-level anatomy

```
<project>/
├── src/
│   ├── backend/             # THE backend — single-backend projects only
│   ├── services/<name>/     # multi-backend projects: one subtree per service
│   ├── frontend/            # web frontend (nextjs, vue-nuxt, …)
│   ├── mobile/              # mobile app (react-native, flutter, …)
│   └── shared/
│       ├── contracts/       # OpenAPI / proto / json-schema — the ONLY
│       │                    # cross-language boundary
│       └── <lang>/          # same-language shared code (go/, ts/, py/)
├── docs/ · .coding-os/ · AGENTS.md · Makefile
```

Rules:

1. **One owner per subtree.** A stack writes only inside its declared
   `structure.root` (enforced by scaffold-boundary; see
   `enforce-scaffold-boundary.sh`).
2. **Languages never share a subtree.** Cross-language communication goes
   through `src/shared/contracts/` artifacts only — never direct imports.
3. **Same-language reuse** lives in `src/shared/<lang>/`; promote code there
   when a second service needs it (reuse-first; nudge ships with TASK-366).

## Multi-backend relocation rule

When a project composes **two or more stacks that declare the same
`structure.root`** (e.g. go-fiber + fastapi, both `src/backend/`), `cos init`
relocates each colliding stack's scaffold subtree to
`src/services/<stack-id>/`. Single-owner roots stay exactly where they are —
existing single-backend projects are untouched.

The relocation is purely path-prefix rewriting at scaffold-copy time; the
stack's inner tree (declared in `structure.tree`) is preserved beneath the
new root. Glob/verify/boundary propagation for relocated services is
TASK-355 (regen-chain parameterization) — until it lands, relocated services
get scaffolding but the enforcement globs still reference the declared root
(documented coupling, tracked on the board).

## Per-stack `structure` declaration

Each `stack.yaml` declares:

```yaml
structure:
  root: src/backend            # the subtree this stack owns
  tree: |                      # canonical inner layout (reference for agents)
    src/backend/
    ├── cmd/<binary>/
    └── internal/{domain,ports,adapters}
  notes: "hexagonal: domain/ports/adapters; internal/-centric per Go community convention"
```

Canonical inner trees (research-grounded, 2025/2026 community conventions):

| Language / stack | Inner convention |
|---|---|
| Go (plain, chi, fiber) | `internal/`-centric; hexagonal `internal/{domain,ports,adapters}` + `cmd/<binary>`; avoid pkg-maximalism |
| Python (fastapi) | `app/{api,services,db,schemas}` — thin routes, logic in services |
| Python (django) | apps-per-domain under the project package |
| TypeScript (nextjs) | `app/` router + `components/ lib/` |
| TypeScript (plain) | `src/index.ts` entry, strict tsconfig |
| React Native | `src/mobile/{screens,components,navigation,hooks}` |

## See also

- [scaffold-boundary contract](../../src/templates/_base/scaffold/docs/governance/scaffold-boundary-contract.md) — per-stack write boundaries
- [template-authoring.md § Language layer](../playbooks/template-authoring.md) — language/extends composition
- [hub-architecture.md § Symlink health](hub-architecture.md) — propagation
