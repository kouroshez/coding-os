---
name: typescript
tier: quality
domain: [frontend, backend]
description: Write type-safe TypeScript that catches bugs at compile time — strict config, type narrowing, discriminated unions, generics, utility types, and avoiding the any/!-escape-hatches that silently disable the checker. Use when setting up tsconfig, modeling a domain with types, fixing "type X is not assignable", deciding unknown vs any, narrowing a union, writing a generic, or reviewing TS for type-safety holes. Underpins React/Next/React-Native/Node. Triggers — "tsconfig", "type error", "TypeScript", "any vs unknown", "generic", "discriminated union", "type narrowing", any `*.ts`/`*.tsx`. Pairs with clean-code (naming/structure), nextjs-react + react-native-mobile (the frameworks), node-backend (server TS), state-management (typed stores).
globs: ""
paths: []
last_reviewed: "2026-06-04"
versions_ref: versions.json
---

# TypeScript

TypeScript is only as safe as its strictness lets it be. With `strict` off (or `any`/`!` sprinkled in) it's JavaScript with extra syntax — the checker is on but blindfolded. The craft is letting the type system *prove* the bug can't happen, not narrating types after the fact.

> Check a tsconfig for the strict flags that actually matter:
> `python3 scripts/check_tsconfig.py tsconfig.json`

## Strict is the floor

```jsonc
// tsconfig.json — the flags that catch real bugs
{
  "compilerOptions": {
    "strict": true,                       // the umbrella — turn it on, always
    "noUncheckedIndexedAccess": true,     // arr[i] is T | undefined (it really is!)
    "noImplicitOverride": true,
    "exactOptionalPropertyTypes": true,
    "noFallthroughCasesInSwitch": true
  }
}
```

`strict: true` enables `noImplicitAny`, `strictNullChecks`, and more — without it, `null`/`undefined` are assignable everywhere and the #1 class of runtime crash goes uncaught. `noUncheckedIndexedAccess` is the highest-value non-default: it makes `arr[i]` honestly `T | undefined`. Full rationale → [references/strictness.md](references/strictness.md).

## `unknown`, never `any`

```typescript
// Wrong — any disables the checker for everything downstream; the bug ships
function parse(json: string): any { return JSON.parse(json); }
const u = parse(s); u.naem.toUpperCase();   // typo compiles, crashes at runtime

// Correct — unknown forces you to narrow before use
function parse(json: string): unknown { return JSON.parse(json); }
const u = parse(s);
if (isUser(u)) u.name.toUpperCase();         // narrowed via a type guard
```

`any` is a hole in the type system that spreads — every value derived from an `any` is `any`. `unknown` is the safe top type: you must narrow it before you touch it. Reserve `any` for genuinely untypable third-party seams, and isolate it behind a typed wrapper.

## Discriminated unions over optional-flag soup

```typescript
// Wrong — every field optional; illegal combinations compile
type Result = { ok?: boolean; data?: User; error?: string };

// Correct — a discriminant makes illegal states unrepresentable
type Result =
  | { status: "ok"; data: User }
  | { status: "error"; error: string };

function render(r: Result) {
  if (r.status === "ok") r.data;     // narrowed — r.error doesn't exist here
  else r.error;                       // exhaustive
}
```

Model state as a union with a `status`/`kind` discriminant so the compiler narrows each branch and rejects impossible combinations. Add a `never` default in the switch for exhaustiveness — adding a variant then becomes a compile error until handled. Patterns → [references/type-system.md](references/type-system.md).

## Narrow, don't assert

```typescript
// Wrong — ! and `as` LIE to the compiler; they don't check anything
const el = document.querySelector(".btn")!;   // crashes if null
const user = data as User;                      // no validation at all

// Correct — narrow with a real check, or validate at the boundary
const el = document.querySelector(".btn");
if (!el) throw new Error("button missing");
const user = userSchema.parse(data);            // zod/valibot validates AND types
```

`!` (non-null) and `as` (type assertion) silence the checker without proving anything — they're `any` in disguise. Validate external data (API responses, JSON, env) at the boundary with a schema validator (zod/valibot) that returns a typed value. `satisfies` checks a literal against a type *without* widening it.

## Generics — constrain, don't over-parameterize

```typescript
// Correct — constrained generic preserves the input type through the function
function first<T>(arr: readonly T[]): T | undefined { return arr[0]; }
function pluck<T, K extends keyof T>(obj: T, key: K): T[K] { return obj[key]; }
```

A generic earns its place when it *links* types (input element → output element). If a type parameter appears once, it's just `unknown` with extra letters — drop it. Use the built-in utility types (`Partial`, `Pick`, `Omit`, `Record`, `ReturnType`) before hand-rolling.

## Anti-patterns (reject on sight)

- `strict: false` (or absent) → the checker is blindfolded; turn it on.
- `any` outside a justified, isolated third-party seam → use `unknown` + narrow.
- `!` non-null assertion to silence a nullable → narrow with an `if`.
- `as SomeType` on external data → validate with a schema at the boundary.
- `@ts-ignore` / `@ts-expect-error` with no comment → if you must, say why.
- Optional-flag object where a discriminated union models the states.
- A generic type parameter used exactly once → it's `unknown`; remove it.

## See also

- [references/strictness.md](references/strictness.md) — every strict flag, what bug it catches, migration order.
- [references/type-system.md](references/type-system.md) — narrowing, unions, generics, utility/conditional/mapped types.
- [assets/typescript-checklist.md](assets/typescript-checklist.md) — the review gate.
- [clean-code](../clean-code/SKILL.md) · [state-management](../state-management/SKILL.md) — and your stack's framework skill (nextjs-react / react-native-mobile / node-backend) when present.
