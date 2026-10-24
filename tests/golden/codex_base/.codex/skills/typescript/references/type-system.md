<!-- domain:FRONTEND | layer:reference | ssot:true | updated:2026-06-04 -->
# TypeScript Type System — Narrowing, Unions, Generics

> P: The type-level moves that make illegal states unrepresentable and bugs compile errors.
> R: Modeling a domain, narrowing a value, or writing a reusable generic.
> S: tsconfig flags — see [strictness.md](strictness.md).
> N: [SKILL.md](../SKILL.md), [typescript-checklist.md](../assets/typescript-checklist.md)

> Nav: [Skill](../SKILL.md)

## Narrowing — let control flow refine the type

```typescript
function len(x: string | string[]): number {
  if (typeof x === "string") return x.length;   // x: string here
  return x.length;                                // x: string[] here
}
```

The compiler narrows by `typeof`, `instanceof`, `in`, truthiness, equality, and
**user-defined type guards** (`function isUser(x: unknown): x is User`). A guard
that returns `x is T` teaches the compiler to narrow at every call site — far
safer than `as T`.

## Discriminated unions + exhaustiveness

```typescript
type Shape =
  | { kind: "circle"; r: number }
  | { kind: "rect"; w: number; h: number };

function area(s: Shape): number {
  switch (s.kind) {
    case "circle": return Math.PI * s.r ** 2;
    case "rect":   return s.w * s.h;
    default: { const _exhaustive: never = s; return _exhaustive; }
  }
}
```

The `never` default makes adding a new `kind` a **compile error** until you handle
it — the type system enforces completeness. Model every "one of N states" this way.

## Generics — link types, don't decorate

```typescript
function map<T, U>(arr: readonly T[], f: (x: T) => U): U[] { return arr.map(f); }
function prop<T, K extends keyof T>(o: T, k: K): T[K] { return o[k]; }
```

A generic is earned when a type parameter appears in **two** positions and links
them (input → output). `K extends keyof T` constrains the key to the object's
real keys, so `prop(user, "naem")` is a compile error.

## Utility & mapped types — reach for built-ins first

| Need | Built-in |
|---|---|
| all optional | `Partial<T>` |
| all required | `Required<T>` |
| subset of keys | `Pick<T, "a" \| "b">` |
| drop keys | `Omit<T, "id">` |
| dict | `Record<K, V>` |
| function's return | `ReturnType<typeof fn>` |
| element of array | `T[number]` |

```typescript
// derive types from a single source instead of redeclaring
const ROLES = ["admin", "user", "guest"] as const;
type Role = typeof ROLES[number];                 // "admin" | "user" | "guest"
```

Deriving types from a `const` (or a zod schema via `z.infer`) keeps one source of
truth — the type can't drift from the value. Mapped + conditional types
(`{ [K in keyof T]: ... }`, `T extends U ? X : Y`) build on these; reach for them
only when a built-in doesn't fit.

## `satisfies` — check without widening

```typescript
const config = { port: 8080, host: "0.0.0.0" } satisfies Record<string, string | number>;
config.port;   // still typed as number (not widened to string | number)
```

`satisfies` validates a literal against a type while keeping the narrow inferred
type — better than `: Type` (which widens) or `as Type` (which doesn't check).
