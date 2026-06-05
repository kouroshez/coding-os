<!-- domain:FRONTEND | layer:asset | ssot:false | updated:2026-06-04 -->
# TypeScript Review Checklist

Run before merging TS/TSX.

## Config
- [ ] `strict: true` (non-negotiable).
- [ ] `noUncheckedIndexedAccess: true`.
- [ ] `noImplicitOverride`, `exactOptionalPropertyTypes`, `noFallthroughCasesInSwitch` on.
- [ ] `python3 scripts/check_tsconfig.py tsconfig.json` → `clean`.

## Type safety
- [ ] No `any` except a justified, isolated third-party seam (commented).
- [ ] External data (API/JSON/env) validated at the boundary with a schema (zod/valibot) — not `as`.
- [ ] No `!` non-null assertions silencing a real nullable — narrowed with a check.
- [ ] No `@ts-ignore`/`@ts-expect-error` without a why comment.
- [ ] Multi-state values modeled as discriminated unions, with a `never` exhaustiveness default.
- [ ] Generics link ≥2 type positions (no single-use type parameters).
- [ ] Types derived from a single source (`as const`, `z.infer`) — not duplicated.

## Hygiene
- [ ] `tsc --noEmit` passes with zero errors (no suppressed-but-broken files in new code).
- [ ] Public function signatures fully typed (params + return), not inferred-and-hoped.
- [ ] `make skills-check-versions` — TS version pin current.
