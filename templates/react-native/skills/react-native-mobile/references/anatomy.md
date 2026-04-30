<!-- domain:REACTNATIVE | layer:reference | ssot:true | updated:2026-04-29 -->
# React Native Anatomy

> P: Canonical file map and entity recipes for the React Native + Expo stack.
> R: Adding any `.ts` / `.tsx` under `mobile/`, or routing a mobile task.
> S: Working on web / backend / ai-service code.
> N: [SKILL.md](../SKILL.md), [scaffold-boundary.yaml](../../../scaffold-boundary.yaml)

> Nav: [Skill](../SKILL.md)

---

## 1. Boundary

SSOT: [`templates/react-native/scaffold-boundary.yaml`](../../../scaffold-boundary.yaml).

## 2. Layout map

| Pattern | Location | Naming | Imports from | Description |
|---|---|---|---|---|
| Tab screen | `mobile/app/(tabs)/<name>.tsx` | `<name>.tsx` | `@/components`, `@/lib` | Tab-bar route |
| Stack screen | `mobile/app/<name>.tsx` | `<name>.tsx` | `@/components`, `@/lib` | Outside tab bar |
| Layout | `mobile/app/_layout.tsx` | `_layout.tsx` (literal) | `@/components` | Navigator |
| Component | `mobile/components/<area>/<name>.tsx` | `kebab-case.tsx` | `@/lib` | Stateless preferred |
| Hook | `mobile/lib/hooks/use<Name>.ts` | `useFooBar.ts` | none cross-area | Pure React hook |
| API helper | `mobile/lib/api/<resource>.ts` | `<resource>.ts` | `@/shared/contracts` | Mapped errors |
| Store slice | `mobile/store/<slice>.ts` | `<slice>.ts` | none cross-area | Zustand slice |
| Sync action | `mobile/sync/<name>.ts` | `<name>.ts` | `@/store` | Offline queue |
| Native bridge | `mobile/native/<name>.{ts,swift,kt}` | `<name>.<ext>` | none | ADR required |
| Theme | `mobile/lib/theme/<name>.ts` | `<name>.ts` | `@/shared/contracts/design-tokens` | Re-export only |
| Test | `mobile/<…>.test.{ts,tsx}` | `<file>.test.tsx` | source under test | Colocated |
| E2E flow | `mobile/e2e/<flow>.yaml` | `<flow>.yaml` | none | Maestro |
| Asset | `mobile/assets/<kind>/<name>.<ext>` | kebab-case | none | Images, fonts |

## 3. Entity recipes

### Add a new component

- **Trigger:** "add a Button / Card / Avatar".
- **Files:**
  1. `mobile/components/<area>/<name>.tsx`
  2. `mobile/components/<area>/<name>.test.tsx`
- **Steps:**
  1. Stateless default; lift state to the screen.
  2. Style via StyleSheet.create OR utility classes (NativeWind) — pick one per stack.
  3. Add `accessibilityRole` / `accessibilityLabel` for every Pressable / Touchable.
  4. Author colocated test (Given/When/Then).

### Add a new screen

- **Trigger:** "add a profile screen", "new screen for X".
- **Files:**
  1. `mobile/app/(tabs)/<name>.tsx` OR `mobile/app/<name>.tsx`
  2. `mobile/app/<name>.test.tsx`
- **Steps:**
  1. Decide tab vs stack — tab if user spends time, stack if modal/detail.
  2. Implement three-state async UI (loading / error / empty / content).
  3. Wire navigation via `router.push('<name>')`; type params in `mobile/lib/navigation/types.ts`.
  4. Add screen-level analytics event on mount.
- **Generator:** [`scripts/new_screen.py`](../scripts/new_screen.py).

### Add a new hook

- **Trigger:** "extract into useFoo".
- **Files:**
  1. `mobile/lib/hooks/use<Name>.ts`
  2. `mobile/lib/hooks/use<Name>.test.ts`
- **Steps:**
  1. Hook MUST start with `use`.
  2. Storage layered on `mobile/lib/storage.ts` — never `AsyncStorage` direct.
  3. Memoize stable values; expose typed return.

### Add a new API helper

- **Trigger:** "wrap GET /users", "call X endpoint".
- **Files:**
  1. `mobile/lib/api/<resource>.ts`
  2. `mobile/lib/api/<resource>.test.ts`
- **Steps:**
  1. `fetch` wrapped by `mobile/lib/api/_client.ts` (timeout, retry, base URL).
  2. Validate response against `shared/contracts/<resource>.ts`.
  3. Map errors to `<ResourceError>` envelope.
  4. Auth tokens read from secure storage at call time — never module scope.

### Add a new store slice

- **Trigger:** "share state across screens".
- **Files:**
  1. `mobile/store/<slice>.ts`
  2. `mobile/store/<slice>.test.ts`
- **Steps:**
  1. Default Zustand; one slice per concern.
  2. Selectors exported alongside slice — components subscribe to selectors.
  3. Persisted slices use `mobile/store/_persist.ts` middleware.

### Add a new sync action

- **Trigger:** "log medication offline", "queue this mutation".
- **Files:**
  1. `mobile/sync/<action>.ts`
  2. `mobile/sync/<action>.test.ts`
- **Steps:**
  1. Define `<Action>Payload` type colocated.
  2. Implement `enqueue()` and `apply()`.
  3. Test with fake offline drainer.
  4. Conflict surfaces via `<ConflictModal />`; never silently drop.

### Add a new test

- **Trigger:** every component / hook / helper / slice / action requires colocated test.
- **Files:**
  1. `<source>.test.{ts,tsx}` — same dir as source.
- **Steps:**
  1. Jest + `@testing-library/react-native`.
  2. Given/When/Then; happy + ≥1 failure path.

## 4. Conventions

#### Naming

- Files: `kebab-case.{ts,tsx}` — exception: Expo Router special names (`_layout.tsx`, `(tabs)/index.tsx`, `[id].tsx`).
- Components: `PascalCase` exported symbol.
- Hooks: `useCamelCase` symbol; file `useCamelCase.ts`.
- Store slices: `<noun>Slice` symbol; file `<slice>.ts`.
- Sync actions: `<verb><Noun>Action` symbol; file `<verb>-<noun>.ts`.
- Constants: `SCREAMING_SNAKE_CASE`.

#### Test colocation

Colocated. `medication/dose-card.tsx` ⇄ `medication/dose-card.test.tsx`. E2E flows under `mobile/e2e/<flow>.yaml`. No `__tests__/` mirrors.

#### Dependency rules

- ✓ `mobile/` may import from `shared/`, `shared/types/`, `shared/contracts/`.
- ✗ `mobile/` may NOT import from `frontend/`, `backend/`, `ai-service/`.
- ✓ `mobile/components/` may import from `mobile/lib/` and `mobile/store/`.
- ✗ `mobile/lib/` may NOT import from `mobile/components/` (one-way).
- ✗ `mobile/store/` may NOT import from `mobile/components/` (state below view).
- ✓ `mobile/sync/` may import from `mobile/store/` and `mobile/lib/api/`.
- ✗ Worklets may NOT call JS-thread APIs (`fetch`, `console.log`) — bridge via `runOnJS`.
