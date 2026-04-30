<!-- domain:REACTNATIVE | layer:policy | ssot:true | updated:2026-04-29 -->
# React Native — stack rules

> P: Compact rule list applied to every `mobile/**/*.{ts,tsx}` file in addition to clean-code, frontend-fundamentals, and a11y.
> R: Reviewing or writing any mobile code.
> S: Touching the web frontend or backend.
> N: [skills/react-native-mobile/SKILL.md](../skills/react-native-mobile/SKILL.md), [skills/react-native-mobile/references/anatomy.md](../skills/react-native-mobile/references/anatomy.md)

## Hard rules

1. **Three-state UI.** Every data-fetching screen handles loading / error / empty / content explicitly.
2. **Worklets are pure.** Functions marked `'worklet'` MUST NOT call JS-thread APIs.
3. **No raw AsyncStorage.** Use `mobile/lib/storage.ts` so storage adapters can swap in tests.
4. **No hard-coded design tokens.** Read from `shared/contracts/design-tokens.ts`.
5. **a11y on every interactive element.** `accessibilityRole` + `accessibilityLabel` mandatory.
6. **Offline mutations queue.** User-mutating actions go through `mobile/sync/queue.ts` — never direct API calls during a write.
7. **Native bridges require an ADR.** No fork to Swift / Kotlin without `docs/architecture/adr/ADR-NNN-*.md`.
8. **Boundary.** May import from `shared/`. Never from `frontend/`, `backend/`, `ai-service/`.

## Pre-commit checklist

- [ ] Three-state branches present.
- [ ] No JS-thread call inside a `'worklet'` function.
- [ ] `accessibilityRole` set on every Pressable / Touchable.
- [ ] Imports respect `templates/react-native/scaffold-boundary.yaml`.
- [ ] Tests colocated and Given/When/Then.
