<!-- domain:FRONTEND | layer:reference | ssot:true | updated:2026-06-04 -->
# TypeScript Strictness — Every Flag, What It Catches

> P: The compiler flags that turn TS from "JS with syntax" into a real prover, and the order to adopt them.
> R: Setting up or tightening a tsconfig; deciding which flags to enable.
> S: Type-level modeling — see [type-system.md](type-system.md).
> N: [SKILL.md](../SKILL.md), [typescript-checklist.md](../assets/typescript-checklist.md)

> Nav: [Skill](../SKILL.md)

## `strict: true` — the umbrella

Turning on `strict` enables all of these at once. Each catches a real bug class:

| Sub-flag | Catches |
|---|---|
| `noImplicitAny` | a parameter/variable that silently became `any` |
| `strictNullChecks` | using a value that can be `null`/`undefined` without a check (the #1 crash) |
| `strictFunctionTypes` | unsound function-parameter variance |
| `strictBindCallApply` | wrong args to `.bind`/`.call`/`.apply` |
| `strictPropertyInitialization` | a class field never assigned in the constructor |
| `useUnknownInCatchVariables` | `catch (e)` is `unknown`, not `any` |

Never ship `strict: false`. If migrating a legacy codebase, enable `strict` and
suppress file-by-file with `// @ts-nocheck` at the top of not-yet-fixed files —
so new code is strict and the debt is visible and shrinking.

## High-value non-defaults (enable these too)

| Flag | What changes | Why it matters |
|---|---|---|
| `noUncheckedIndexedAccess` | `arr[i]` and `obj[key]` become `T \| undefined` | array/record access really can be undefined — this makes the checker admit it |
| `exactOptionalPropertyTypes` | `{ x?: T }` ≠ `{ x: T \| undefined }` | distinguishes "absent" from "present but undefined" |
| `noImplicitOverride` | `override` keyword required to override | a renamed base method silently stops being overridden otherwise |
| `noFallthroughCasesInSwitch` | a `case` with no `break`/`return` errors | classic switch fall-through bug |
| `noImplicitReturns` | all code paths must return | a missing return branch |

`noUncheckedIndexedAccess` is the single most valuable non-default — it surfaces a
huge class of "cannot read property of undefined" before runtime.

## Adoption order for an existing project

1. `strict: true` — fix the null-check errors first (biggest payoff).
2. `noUncheckedIndexedAccess` — expect many `arr[i]` sites; add guards or `?.`.
3. The override/switch/return flags — usually few errors, quick wins.
4. `exactOptionalPropertyTypes` — last; it's the most pedantic.

## Verify

`python3 ../scripts/check_tsconfig.py tsconfig.json` flags any of the above that
are off or missing. Note: it does not resolve `extends` — if your config extends
a base, a flag may be inherited; check the resolved output with
`tsc --showConfig`.
