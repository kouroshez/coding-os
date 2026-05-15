<!-- domain:REACTNATIVE | layer:policy | ssot:true | updated:2026-04-29 -->
# Mobile Engineering Rules

> P: Rules every `src/mobile/**/*.{ts,tsx}` file must satisfy. Layered on top of clean-code, frontend-fundamentals, and a11y.
> R: Reviewing or writing any mobile source file.
> S: Touching the web frontend or backend.
> N: [offline-first.md](offline-first.md), [accessibility-checklist.md](accessibility-checklist.md), [../playbooks/mobile-app.md](../playbooks/mobile-app.md)

## 1. Architecture

- Expo SDK + React Native 0.74+. Use Expo Router for navigation.
- One root `_layout.tsx` per route segment.
- State: hooks-local first, Zustand slice for cross-screen.
- Style: StyleSheet.create OR utility-first (NativeWind) — pick one per stack, never mix.
- Theme: tokens live in `src/shared/contracts/design-tokens.ts`, re-exported via `src/mobile/lib/theme/`.

## 2. Performance

- Screen TTI ≤ 600 ms on Pixel 5 / iPhone 13.
- Animations 60 fps — verify with Reanimated profiler.
- Image budget ≤ 200 KB per screen — `expo-image` mandatory.
- Avoid `Animated` (legacy); prefer Reanimated v3 + worklets.

## 3. Worklets

- Functions running on the UI thread MUST start with `'worklet';`.
- Worklets MAY NOT call `fetch`, `console.log`, `setTimeout`. Bridge via `runOnJS()`.
- Shared values via `useSharedValue`, never `useState` for animation.

## 4. Storage

- All persistent storage goes through `src/mobile/lib/storage.ts`.
- Sensitive values (auth tokens, PII) use `expo-secure-store` — exposed via `src/mobile/lib/secure-storage.ts`.
- Tests inject a fake storage adapter — never read the real keychain in test mode.

## 5. Networking

- All HTTP via `src/mobile/lib/api/_client.ts` (timeout, retry, base URL, auth header).
- Validate responses against `src/shared/contracts/<resource>.ts` schema.
- Map errors to `<ResourceError>` envelope from `src/shared/contracts/errors.ts`.
- Never call `fetch` directly from a screen / component.

## 6. Tests

- Colocated `.test.{ts,tsx}` next to source.
- Given/When/Then in test names.
- Snapshots only for static screens; never for hook-driven UI.
- E2E flows live in `src/mobile/e2e/<flow>.yaml` — Maestro.

## 7. Accessibility

See [accessibility-checklist.md](accessibility-checklist.md). Every interactive element MUST carry `accessibilityRole`, `accessibilityLabel`, and `accessibilityState`. Test with VoiceOver + TalkBack before merge.

## 8. Boundary

`src/mobile/` may import from `src/shared/`. Never from `src/frontend/`, `src/backend/`, `src/ai-service/`. Cross-stack contracts live in `src/shared/types/` and `src/shared/contracts/`. SSOT: [`src/templates/react-native/scaffold-boundary.yaml`](../../../scaffold-boundary.yaml).
