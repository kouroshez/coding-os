<!-- domain:REACTNATIVE | layer:reference | ssot:true | updated:2026-06-27 -->
# React Native Anatomy

> P: Canonical file map + entity recipes for the React Native (Expo-compatible) stack.
> R: Adding any `.ts`/`.tsx` under `src/mobile/`, or routing a mobile task.
> S: Reading backend / web code — wrong stack.
> N: [SKILL.md](../SKILL.md), [scaffold-boundary.yaml](../../../scaffold-boundary.yaml)

> Nav: [Skill](../SKILL.md)

---

## 1. Boundary

SSOT: `src/templates/react-native/scaffold-boundary.yaml`.

## 2. Layout map

| Pattern | Location | Naming | Imports from | Description |
|---|---|---|---|---|
| Screen | `screens/<Feature>Screen.tsx` | `<Feature>Screen.tsx` | hooks, components | One screen per route; presentational + a hook |
| Component | `components/<Name>.tsx` | `<Name>.tsx` | — | Reusable presentational component |
| Hook | `hooks/use<Name>.ts` | `use<Name>.ts` | services | State + data access (the logic layer) |
| Navigation | `navigation/<Name>Navigator.tsx` | `<Name>Navigator.tsx` | screens | Route tree (React Navigation) |
| Test | `<file>.test.tsx` | `<file>.test.tsx` | source under test | Jest + Testing Library |

## 3. Entity recipes

### Add a new screen
- **Trigger:** "add a `<Feature>` screen / route".
- **Files emitted:**
  1. `screens/<Feature>Screen.tsx`
  2. `hooks/use<Feature>.ts`
  3. `screens/<Feature>Screen.test.tsx`
- **Steps:**
  1. Screen reads state from `use<Feature>` and renders; no logic inline.
  2. Register the screen in the navigator.

### Add a new component
- **Trigger:** "extract a reusable view".
- **Files emitted:** `components/<Name>.tsx` (+ test).
- **Steps:**
  1. Props-driven, no data fetching — pass data in.

### Add a new test
- **Trigger:** any new screen / component / hook.
- **Files emitted:** `<file>.test.tsx` next to source.
- **Steps:**
  1. `render` + `screen` queries; `renderHook` for hooks.

## 4. Conventions

#### Naming
- Components / screens: `PascalCase.tsx`. Hooks: `use<Name>.ts`.

#### Test colocation
- Colocated: `<file>.test.tsx` next to source.

#### Dependency rules
- ✓ screen → hook → service.
- ✗ a component never fetches data — a hook does.
- ✗ `src/mobile/` never imports from `src/frontend/` / `src/backend/` — share via `src/shared/`.
