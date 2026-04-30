---
name: react-native-mobile
description: Use when creating or modifying React Native screens, components, hooks, or native bridges in the mobile app. Triggers on any .ts/.tsx file change under mobile/. Covers Hermes + Reanimated worklet constraints, three-state async UI, offline-first sync queues, navigation patterns, and a11y for VoiceOver / TalkBack.
globs: "mobile/**/*.{ts,tsx}"
depends_on:
  - clean-code
  - frontend-fundamentals
  - a11y
---

This skill enforces React Native + Expo conventions for the `mobile/` subtree. It `depends_on: [clean-code, frontend-fundamentals, a11y]` — universal code quality, three-state async UI, and accessibility checks load transitively. This skill adds ONLY mobile-specific concerns on top.

Anatomy reference: [`references/anatomy.md`](references/anatomy.md). Read that file BEFORE writing any new screen / component / hook.

## Pre-Code Checklist

Before writing or modifying any `.ts` / `.tsx` file under `mobile/`:

- [ ] Read [`references/anatomy.md`](references/anatomy.md) — file map and entity recipes.
- [ ] If touching a screen: read `docs/playbooks/mobile-app.md`.
- [ ] If touching offline / sync: read `docs/engineering/offline-first.md`.
- [ ] If touching animation: confirm worklet vs JS thread split.
- [ ] If touching API calls: read `docs/api-contracts/error-format.md`.

## 1. Architecture defaults

- **Navigation:** React Navigation v7 (stack + tabs). Every route lives under `mobile/app/(tabs)/<route>` or `mobile/app/<route>` if outside the tab bar.
- **State:** prefer hooks-local state. Cross-screen state goes through `mobile/store/` (Zustand by default; swap is a stack-wide decision, not per-feature).
- **Styling:** StyleSheet API for static styles, NativeWind / Tailwind RN for utility-first when configured. NEVER inline `style={{ }}` for repeated tokens.
- **Theming:** read tokens from `shared/contracts/design-tokens.ts` — never hard-code colors / spacing.

## 2. Three-state async UI (mandatory)

Every screen that fetches data MUST handle three states explicitly:

```tsx
if (loading) return <Skeleton />;
if (error)   return <ErrorView onRetry={retry} message={mapError(error)} />;
if (!data)   return <EmptyState />;
return <Content data={data} />;
```

If only happy path renders → fail in PR review.

## 3. Hermes + Reanimated worklet rules

- Functions executed on the UI thread MUST be marked with `'worklet'`:

  ```tsx
  const onScroll = useAnimatedScrollHandler({
    onScroll: (event) => {
      'worklet';
      scrollY.value = event.contentOffset.y;
    },
  });
  ```

- Worklets MAY NOT call JS-thread APIs (`fetch`, `console.log`). Use `runOnJS()` to bridge.
- `useSharedValue` for animated values; never `useState` for animation state.

## 4. Offline-first + sync queue

For any user-mutating action (log medication, save profile, post message):

1. Optimistically update local state via Zustand action.
2. Append the action to `mobile/sync/queue.ts`.
3. When connectivity returns, drain the queue with `mobile/sync/drainer.ts`.
4. Surface conflicts via `<ConflictModal />` — never silently drop user data.

Pattern source: `docs/engineering/offline-first.md`.

## 5. Accessibility (a11y)

- Every interactive element MUST carry `accessibilityRole`, `accessibilityLabel`, and `accessibilityState`.
- Test with VoiceOver (iOS) AND TalkBack (Android). Both ship in CI.
- Focus management on screen change: use `AccessibilityInfo.announceForAccessibility(...)`.
- Color contrast ≥ WCAG 2.2 AA — see `docs/engineering/accessibility-checklist.md`.

## 6. Performance budgets

- Screen TTI ≤ 600 ms on a Pixel 5 / iPhone 13.
- Animations run at 60 fps — verify with Reanimated profiler before merge.
- Image budget ≤ 200 KB per screen — use `expo-image` with `contentFit="cover"`.
- Bundle: track size via `npx react-native-bundle-visualizer` per release.

## 7. Native bridges

Only fork to native code (Swift / Kotlin) when:

1. The feature is impossible in JS (e.g. background tasks, hardware sensors).
2. A maintained Expo or RN package does not cover it.
3. ADR exists in `docs/architecture/adr/` documenting the decision.

Otherwise: stay in TypeScript.

## 8. Test discipline

- Unit tests colocated: `mobile/components/foo/foo.test.tsx`.
- Snapshot tests for static screens only — never for hook-driven UI.
- E2E with Maestro: `mobile/e2e/<flow>.yaml`.
- Fast: `npm test --watch` must run < 3 s on the changed file.

## 9. Boundary

`mobile/` may import from `shared/`. Never from `frontend/`, `backend/`, or `ai-service/`. Cross-stack contracts live in `shared/types/` and `shared/contracts/`.

Boundary SSOT: [`templates/react-native/scaffold-boundary.yaml`](../../scaffold-boundary.yaml).
