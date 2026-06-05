---
name: react-native-patterns
description: React Native 0.76+ (New Architecture) patterns specific to bare RN apps with TypeScript. Use when writing or reviewing screens, hooks, native modules, navigation, or anything platform-specific in a bare React Native project. Covers the New Architecture (Fabric + TurboModules), Hermes-aware code, JSI bridges, expo-friendly patterns when relevant, and the cohabitation of TypeScript-side code with Swift/Kotlin native modules. Pairs with mobile-fundamentals (cross-platform mobile concerns) and frontend-fundamentals (generic React).
tier: stack
domain: [mobile]
last_reviewed: "2026-05-11"

---

# React Native (Bare) — Patterns

For React Native 0.76+ where the New Architecture is the default. Bare RN, not Expo (Expo gets its own template later). TypeScript throughout. Hexagonal client architecture (see src/core/skills/hexagonal-architecture).

## When to Use This Skill

- Writing or reviewing a `.tsx` screen / `.ts` hook / `.ts` use case adapter under `src/mobile/src/`.
- Authoring a TurboModule / Fabric component (Swift/Obj-C/Kotlin/Java).
- Touching anything in `src/mobile/ios/` or `src/mobile/android/`.
- Configuring Metro / Hermes / R8 / ProGuard.
- Debugging frame drops, JS-thread blocks, native crashes.

For cross-mobile-platform topics (navigation choices, offline-first, push notifications, deep links) see `mobile-fundamentals`.

## The 0.76+ Baseline

Pin these and assume them everywhere:

- React Native 0.76 or newer (New Architecture default; `newArchEnabled=true`).
- React 18.3+.
- TypeScript 5.5+, `strict: true`, `noUncheckedIndexedAccess: true`.
- Hermes engine (default on both platforms).
- Metro 0.81+ with package exports support.
- Yarn 4 (`berry`) or pnpm — npm classic gets RN dep resolution wrong on edge cases.

If your project pre-dates 0.76, the upgrade is worth doing before adding meaningful new features. The legacy bridge will be removed in 0.79.

## Project Structure

This skill assumes the hexagonal layout (per `hexagonal-architecture` skill, RN section). Critical recap:

```
src/mobile/src/
├── domain/                  # pure TS, no RN imports
├── application/             # use cases + ports
├── infrastructure/          # adapters: http/, storage/, push/, analytics/
├── delivery/                # UI: screens/, navigation/, providers/, components/
└── fakes/                   # in-memory adapters for tests + Storybook
```

The TS source root has **strict isolation** — no `react-native` import inside `domain/`, no `axios` inside `application/`, no `useState` inside `infrastructure/`. ESLint `eslint-plugin-boundaries` enforces this.

## Screens — Thin Inbound Adapters

Screens parse intent → call a use case → render UI states. They DO NOT contain business rules.

```tsx
// src/mobile/src/delivery/screens/lesson/LessonScreen.tsx
import { useQuery } from '@tanstack/react-query';
import { ActivityIndicator, Text, View } from 'react-native';

import { useUseCase } from '@delivery/providers/DependencyProvider';
import { LessonID } from '@domain/primitives/id';
import type { LessonScreenProps } from '../../navigation/types';

export function LessonScreen({ route }: LessonScreenProps) {
  const id = LessonID.parse(route.params.lessonId);
  const getLesson = useUseCase('getLesson');

  const { data, isLoading, isError } = useQuery({
    queryKey: ['lesson', id],
    queryFn: () => getLesson.execute({ lessonId: id }),
    staleTime: 30_000,
  });

  if (isLoading) return <CenteredSpinner />;
  if (isError)   return <ErrorState onRetry={...} />;
  if (!data)     return null;

  return (
    <View accessibilityLabel="Lesson" style={styles.container}>
      <Text style={styles.title}>{data.title}</Text>
      ...
    </View>
  );
}
```

Rules:

- **Three states ALWAYS**: loading, error, ready (+ optionally empty). Never let a query render `data` without checking the others first.
- **No `any`**. Type props from React Navigation. Use `RouteProp<RootStackParamList, 'Lesson'>`.
- **`accessibilityLabel`** on every meaningful container — see `a11y` skill.
- **No business logic** — no calculations, no validation rules, no side-effect orchestration. That's a use case.

## Hooks — Composing UI Concerns

Custom hooks are the right tool for orchestrating UI-side concerns: subscribing to a store, debouncing input, syncing AppState, listening to network.

```tsx
// src/mobile/src/delivery/hooks/useNetworkAware.ts
import NetInfo from '@react-native-community/netinfo';
import { useEffect, useState } from 'react';

export function useNetworkAware(): { online: boolean; type: string | null } {
  const [state, setState] = useState({ online: true, type: null as string | null });

  useEffect(() => {
    const unsub = NetInfo.addEventListener((s) => {
      setState({ online: !!s.isConnected, type: s.type ?? null });
    });
    return unsub;
  }, []);

  return state;
}
```

Rules:

- **One concern per hook.** `useNetworkAware`, `useAppState`, `useDebouncedValue`. NOT `useEverything`.
- **Always return cleanup**. Subscriptions, timers, listeners — all cleaned up in the effect's return.
- **Stable identities for deps**. Use `useCallback` / `useMemo` to keep dep arrays from causing infinite loops.
- **`use*` naming**. Lint enforces `react-hooks/rules-of-hooks`.

## State Management — Use the Right Layer

(Full coverage in `state-management` skill; recap here.)

| State kind | Tool | Why |
|---|---|---|
| **Server state** (cached API responses, mutations) | TanStack Query | Built-in caching, retries, dedupe, stale-while-revalidate. |
| **Global UI state** (auth status, theme, selected tab) | Zustand | Tiny, no provider, integrates with selectors cleanly. |
| **Local component state** | `useState` / `useReducer` | Don't promote to global until 2+ components need it. |
| **Form state** | React Hook Form | Uncontrolled by default = fewer re-renders on each keystroke. |
| **Navigation state** | React Navigation (handled internally) | Don't sync nav state to your own store; let RN Navigation own it. |

Avoid Redux unless you have an existing Redux app or specific need (DevTools time-travel, etc.). Zustand wins on lines-of-code for almost every new project in 2026.

## Navigation — React Navigation 7

Bare RN's canonical navigator is React Navigation. Pin to v7+ (current major as of 2026).

```tsx
// src/mobile/src/delivery/navigation/RootNavigator.tsx
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';

import { HomeScreen } from '../screens/home/HomeScreen';
import { LessonScreen } from '../screens/lesson/LessonScreen';
import type { RootStackParamList } from './types';
import { linking } from './linking';

const Stack = createNativeStackNavigator<RootStackParamList>();

export function RootNavigator() {
  return (
    <NavigationContainer linking={linking}>
      <Stack.Navigator screenOptions={{ headerLargeTitle: true }}>
        <Stack.Screen name="Home"   component={HomeScreen} />
        <Stack.Screen name="Lesson" component={LessonScreen} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
```

```typescript
// src/mobile/src/delivery/navigation/types.ts
import type { NativeStackScreenProps } from '@react-navigation/native-stack';

export type RootStackParamList = {
  Home: undefined;
  Lesson: { lessonId: string };
};

export type LessonScreenProps =
  NativeStackScreenProps<RootStackParamList, 'Lesson'>;
```

Always:

- **Native-stack** (not legacy stack) for the New Architecture's headlines.
- Param types declared centrally + reused via `*ScreenProps`.
- Deep linking config in a separate file — see `mobile-fundamentals`.

## Lists — FlashList, Not FlatList

`@shopify/flash-list` outperforms FlatList by 10–50× on long lists. Mandatory for any list >50 items.

```tsx
import { FlashList } from '@shopify/flash-list';

<FlashList
  data={lessons}
  renderItem={({ item }) => <LessonRow lesson={item} />}
  estimatedItemSize={88}      // REQUIRED — measure once, set close
  keyExtractor={(item) => item.id}
  onEndReached={loadMore}
  onEndReachedThreshold={0.5}
  ListEmptyComponent={EmptyState}
/>
```

Tips:

- `estimatedItemSize` matters — measure your row height (incl margin) and set close to it.
- `getItemType` if rows have wildly different layouts (recycler can't pool different shapes).
- Stable `keyExtractor`; don't generate keys inline.
- Pair with TanStack Query's `useInfiniteQuery` for cursor pagination.

## Forms — React Hook Form

```tsx
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

const SignInSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
});

type SignInForm = z.infer<typeof SignInSchema>;

export function SignInScreen() {
  const { control, handleSubmit, formState: { errors, isSubmitting } } =
    useForm<SignInForm>({ resolver: zodResolver(SignInSchema) });

  const signIn = useUseCase('signIn');

  const onSubmit = async (data: SignInForm) => {
    try {
      await signIn.execute(data);
    } catch (e) {
      // surface domain error
    }
  };

  return (
    <View>
      <Controller
        control={control}
        name="email"
        render={({ field: { value, onChange, onBlur } }) => (
          <TextInput
            value={value}
            onChangeText={onChange}
            onBlur={onBlur}
            autoCapitalize="none"
            keyboardType="email-address"
            accessibilityLabel="Email"
          />
        )}
      />
      {errors.email && <Text>{errors.email.message}</Text>}
      <Button title="Sign In" disabled={isSubmitting} onPress={handleSubmit(onSubmit)} />
    </View>
  );
}
```

Rules:

- **Validation schema lives next to the form**, exported if reused server-side.
- Use **Zod or Valibot**, not Yup (deprecated in 2026 ecosystem direction).
- **No business validation** in the schema (e.g., "promo code valid?") — that's a use case round-trip.
- **`autoCapitalize="none"`** + **`keyboardType`** on email/password/phone fields.

## Native Modules — TurboModules

Add a native module when:

- You need to call a platform API not exposed by RN core or community.
- You need synchronous JS↔native calls (TurboModules support sync; legacy bridge does not).

```typescript
// src/mobile/src/infrastructure/native/SecureStorage.ts
import { TurboModuleRegistry, type TurboModule } from 'react-native';

export interface Spec extends TurboModule {
  set(key: string, value: string, biometric: boolean): Promise<void>;
  get(key: string): Promise<string | null>;
  delete(key: string): Promise<void>;
}

export default TurboModuleRegistry.getEnforcing<Spec>('NativeSecureStorage');
```

iOS implementation skeleton (Swift):

```swift
// src/mobile/ios/NativeSecureStorage.swift
import Foundation
import React

@objc(NativeSecureStorage)
class NativeSecureStorage: NSObject {
  @objc(set:value:biometric:resolve:reject:)
  func set(_ key: String, value: String, biometric: Bool,
           resolve: @escaping RCTPromiseResolveBlock,
           reject: @escaping RCTPromiseRejectBlock) {
    // Use Keychain Services with kSecAttrAccessControl when biometric is true.
    ...
  }
  // ... get / delete
}
```

For most cases use community modules first:

- `react-native-keychain` — Keychain/Keystore wrapper.
- `react-native-device-info` — device metadata.
- `@react-native-community/netinfo` — network state.
- `@react-native-firebase/messaging` (or `@notifee/react-native`) — push.
- `react-native-mmkv` — fast non-secure key-value storage.

Roll your own only when no good community module exists.

## Performance Patterns

### Memoization — Selective, Not Universal

`React.memo` everywhere makes things SLOWER (comparison cost > saved render). Apply when:

- Component re-renders frequently with the same props (e.g., row in a long list).
- Expensive render (heavy computation, big tree).
- Used in many places.

```tsx
const LessonRow = memo(function LessonRow({ lesson }: { lesson: Lesson }) {
  return ...;
}, (prev, next) => prev.lesson.id === next.lesson.id && prev.lesson.updated_at === next.lesson.updated_at);
```

### Avoid Inline Objects/Functions in Props

```tsx
// BAD — new object every render breaks memo
<LessonRow lesson={lesson} style={{ padding: 8 }} onPress={() => open(lesson.id)} />

// GOOD
const ROW_STYLE = { padding: 8 };
const handlePress = useCallback(() => open(lesson.id), [lesson.id]);
<LessonRow lesson={lesson} style={ROW_STYLE} onPress={handlePress} />
```

### Suspend Off-Screen Work

```tsx
import { useFocusEffect } from '@react-navigation/native';

useFocusEffect(useCallback(() => {
  const t = setInterval(refresh, 5_000);
  return () => clearInterval(t);
}, [refresh]));
```

Pause polls/subscriptions when the screen isn't focused. Cuts background CPU + battery.

### Animations — Reanimated 3 Worklets

Use `react-native-reanimated` worklets for any animation that should hit 60/120 FPS. The worklet runs on the UI thread, no JS bridge involvement, no jank when the JS thread is busy.

```tsx
import Animated, { useSharedValue, useAnimatedStyle, withSpring } from 'react-native-reanimated';

function PressableButton({ onPress, children }: Props) {
  const scale = useSharedValue(1);
  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));
  return (
    <Animated.View style={animatedStyle}>
      <Pressable
        onPressIn={() => { scale.value = withSpring(0.95); }}
        onPressOut={() => { scale.value = withSpring(1); }}
        onPress={onPress}>
        {children}
      </Pressable>
    </Animated.View>
  );
}
```

NEVER use the legacy `Animated` API for anything driven by gestures.

### Hermes — Lazy Bytecode + AOT Tweaks

Hermes ships pre-compiled bytecode. Two knobs:

- **Lazy parsing** (default on): only parses what's about to run. Lower startup time.
- **Bytecode optimizations** (`hermes_enable_optimization=true` in `gradle.properties` and `Podfile`): smaller bundle, faster execution. Always on for release.

For full bundle/startup analysis, see Callstack's `react-native-best-practices` (referenced in `performance` skill).

## Hermes-Aware Code — Things to Know

- **No `Function.prototype.toString` round-trip** to dynamically generate code (Hermes doesn't ship a parser at runtime by default).
- **Date / Intl** support is improving but spotty — pin `intl-pluralrules` polyfill for older Hermes versions if you need locale-aware formatting on Android.
- **Proxy is supported** but slower than V8 — avoid in hot paths.

## Native Crashes — What to Do

1. **Sentry** (or Bugsnag, Embrace) installed with native crash handlers (sourcemaps + dSYM uploaded to symbolicate stacks).
2. **Per-platform**: Crashlytics for Firebase users.
3. **Native breadcrumbs** — log JS-side actions that the native handler captures, so the crash report shows what the user did before the crash.
4. **Retry queue** for failed API calls — covered in `mobile-fundamentals` (offline section).

## Testing

Three layers (per the `clean-code` and hexagonal patterns):

1. **Domain + application unit tests** — Vitest or Jest, no RN runtime, fast (5ms each). Use the in-memory `fakes/`.
2. **Component tests** — React Native Testing Library + jest-react-native preset. Render screens with fake use cases via `<DependencyProvider>`. Avoid snapshot tests; assert behavior.
3. **E2E** — Maestro (preferred) or Detox. Few; cover the critical sign-in / make-payment / start-lesson flows.

```typescript
// src/mobile/src/delivery/screens/home/HomeScreen.test.tsx
import { render, screen } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { HomeScreen } from './HomeScreen';
import { DependencyProvider } from '../../providers/DependencyProvider';
import { fakeUseCases } from '@fakes/useCases';

test('renders the recommended lesson', async () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <DependencyProvider value={fakeUseCases({ recommended: { title: 'Hexagons' } })}>
        <HomeScreen />
      </DependencyProvider>
    </QueryClientProvider>
  );
  expect(await screen.findByText('Hexagons')).toBeOnTheScreen();
});
```

## Build + Release

- **iOS**: Xcode 16+, deployment target iOS 16+ (lower means missing passkey APIs).
- **Android**: minSdk 24+ (Android 7), targetSdk 35+ (current as of 2026).
- **Hermes**: enabled in both `Podfile` and `gradle.properties`.
- **R8/ProGuard** for Android release: enabled with the RN-provided rules + your own keep rules for native modules.
- **Bitcode**: deprecated by Apple; nothing to do.
- **App Bundle** (`.aab`) for Play Store, IPA for App Store Connect.

## Common RN Mistakes

1. **AsyncStorage for tokens** — not encrypted; use Keychain via `react-native-keychain`.
2. **Inline styles in render** — re-creates style object every render; use StyleSheet or constant.
3. **`<View>` instead of `<Pressable>`** for tap targets — accessibility loss + no built-in feedback.
4. **`onPress={() => doStuff(arg)}`** in a list row — new function per render; pass `useCallback` or pass arg via `data` from FlashList.
5. **`Dimensions.get('window')` at module scope** — frozen; use `useWindowDimensions()` for orientation changes.
6. **No keyboard avoidance** — text input gets covered by soft keyboard. Use `KeyboardAvoidingView` + `KeyboardAwareScrollView` or `react-native-keyboard-controller`.
7. **Forgetting Android back-button** — `BackHandler` listener for screens with custom back behavior.
8. **`console.log` in release builds** — strip with babel-plugin-transform-remove-console.
9. **Sync calls on JS thread** — RN's main thread; blocks rendering. Use async, defer to `InteractionManager.runAfterInteractions` if heavy.
10. **No `accessibilityLabel`** — VoiceOver / TalkBack reads "button" with no context.
11. **Pre-rendering huge images** — use `react-native-fast-image`, set `resizeMode`, downscale at the source.
12. **Skipping Hermes** — startup time and memory regression.

## Dependencies — Conservative Set

The "small, well-maintained" set this project commits to:

```json
{
  "dependencies": {
    "react": "18.3.1",
    "react-native": "0.76.x",
    "@react-navigation/native": "^7.x",
    "@react-navigation/native-stack": "^7.x",
    "@tanstack/react-query": "^5.x",
    "zustand": "^5.x",
    "react-hook-form": "^7.x",
    "@hookform/resolvers": "^3.x",
    "zod": "^3.x",
    "@shopify/flash-list": "^1.7.x",
    "react-native-reanimated": "^3.x",
    "react-native-gesture-handler": "^2.x",
    "react-native-safe-area-context": "^4.x",
    "react-native-screens": "^4.x",
    "react-native-keychain": "^8.x",
    "react-native-mmkv": "^3.x",
    "@react-native-community/netinfo": "^11.x",
    "react-native-fast-image": "^8.x",
    "@notifee/react-native": "^9.x",
    "axios": "^1.x"
  }
}
```

Each addition needs a 1-paragraph justification in the PR.

## Source Material

- React Native 0.76+ docs (reactnative.dev) — primary.
- Callstack's "Ultimate Guide to React Native Optimization" — bundle/perf bible.
- React Navigation 7 docs — navigation patterns.
- Reanimated 3 + Gesture Handler docs — animation/interaction.
- Shopify FlashList docs + Restyle — list performance + design system.
- React Native New Architecture docs (Fabric / TurboModules / JSI).

## Tooling

Flag list/render performance smells (inline renderItem, missing keyExtractor, inline styles):
`python3 scripts/scan_rn_perf.py src/mobile/**/*.tsx`

## See also

- [references/list-performance.md](references/list-performance.md) — FlatList/FlashList, stable renderItem, StyleSheet, Reanimated.
- [assets/rn-review-checklist.md](assets/rn-review-checklist.md) — the review gate.
