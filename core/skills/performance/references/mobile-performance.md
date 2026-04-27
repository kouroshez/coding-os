# Mobile Performance — React Native Specific

The actual playbook for keeping a React Native app fast on real devices. Pulls from Callstack's optimization guide + Hermes / FlashList / Reanimated documentation.

## Three Categories of Slowness

| Category | Symptom | Where to look |
|---|---|---|
| **Startup** | Cold launch > 2s | Hermes lazy parse, native init, Metro bundle, splash screen |
| **Runtime jank** | Scroll < 60 FPS, animations stutter | JS thread blocks, heavy renders, bridge traffic |
| **Memory / battery** | App killed in background, drains battery | Memory leaks, native modules, unsubscribed listeners |

Each has different tools + fixes. Diagnose first.

## Startup Time (TTI)

### Measure

- **iOS**: Xcode → Instruments → "App Launch" template. Or `xcrun simctl launch --console <bundle-id>` and time it.
- **Android**: `adb shell am start -W com.app/.MainActivity` reports `TotalTime`.
- **In-app**: log `Date.now()` in `index.js` first line and again in `App.tsx`'s first render — diff is JS startup.

### Optimization

1. **Hermes enabled** — required. Both platforms.
2. **Pre-compiled bytecode** — Hermes ships `.hbc` files; Metro builds them in release mode automatically.
3. **Lazy parsing** — Hermes parses functions on first call by default. Don't disable.
4. **Reduce initial bundle**:
   - `import` only what you need (tree-shake).
   - Defer non-critical screens with React Navigation's lazy `getComponent`.
   - Defer non-critical libraries: load analytics / push setup AFTER first render.
5. **Defer native module init** that's not needed at launch.
6. **Splash screen kept until first useful frame** (`react-native-bootsplash`). Better UX than launching to white.
7. **InteractionManager.runAfterInteractions** for non-essential work after navigation.

```typescript
// In App.tsx
useEffect(() => {
  // Defer heavy init until after first paint.
  InteractionManager.runAfterInteractions(() => {
    initAnalytics();
    setupPushHandlers();
    prefetchNextScreens();
  });
}, []);
```

## Frame Rate (60 / 120 FPS)

### Measure

- **In-app**: enable React Native's perf monitor (Cmd+M / Cmd+D → Show Perf Monitor). Shows JS + UI thread FPS.
- **Flipper**: React DevTools Profiler — see component re-renders.
- **Hermes Sampling Profiler**: `hermes -enable-eval -sample-profiler`. Shows where JS time is spent.

### Diagnose

- Drops in **JS thread FPS** during scroll → JS work blocking (re-renders, sync I/O).
- Drops in **UI thread FPS** during animation → native animation issue (rare with Reanimated worklets).
- Stutter only on first scroll → cold native rendering; warm up via FlashList scroll-to-end on mount.

### Optimization

1. **FlashList for any list > 50 items** (per `react-native-patterns`). FlatList = old, slow. FlashList recycles row instances; 10–50× faster.
2. **`useCallback` and `useMemo` aggressively** in row components.
3. **`React.memo`** on row component, with custom equality if needed.
4. **`useNativeDriver: true`** on legacy `Animated` (or use Reanimated, which is always native).
5. **Reanimated 3 worklets** for any gesture-driven animation. Worklets run on UI thread; no bridge involvement.
6. **Avoid `setState` in scroll handlers** without throttle / debounce.
7. **`removeClippedSubviews={true}`** on long ScrollView (Android only; iOS is fine without).

```typescript
// Reanimated 3 worklet — runs on UI thread, 60 FPS guaranteed
import Animated, { useSharedValue, useAnimatedStyle, withSpring } from 'react-native-reanimated';

const scale = useSharedValue(1);
const animatedStyle = useAnimatedStyle(() => ({
  transform: [{ scale: scale.value }],
}));

<Animated.View style={animatedStyle}>...</Animated.View>
<Pressable
  onPressIn={() => { scale.value = withSpring(0.95); }}
  onPressOut={() => { scale.value = withSpring(1); }}>
  ...
</Pressable>
```

## JS Thread — Don't Block

The JS thread runs all React work. Block it = drop frames.

**Measure**: JS FPS drops during scroll / animation in the perf monitor.

**Defenses**:

- **No sync JSON parse > 100KB** in render. Move to `InteractionManager.runAfterInteractions` or a worker.
- **Use `react-native-mmkv`** (synchronous, ~30x faster than AsyncStorage) for small data; AsyncStorage offloads to native thread but has overhead per call.
- **Defer heavy computation**:
  ```typescript
  InteractionManager.runAfterInteractions(() => {
    const result = heavyComputation();
    setState(result);
  });
  ```
- **`useDeferredValue`** in React 18+ for low-priority updates.
- **Background thread** for crypto / image processing: `react-native-fast-tflite` etc. spawn off-thread.

## Bundle Size

### Measure

```bash
# Install:
yarn add -D react-native-bundle-visualizer

# Run:
yarn react-native-bundle-visualizer
# Opens the bundle in browser; click into chunks.
```

### Diagnose

Common offenders:

- **Moment.js** → swap for `date-fns` (tree-shakable) or native `Intl`.
- **Lodash** → `import { debounce } from 'lodash-es'` (tree-shake) OR write your own.
- **lottie-react-native + animations** → keep animation files small (Lottie JSON can balloon).
- **All locale files of i18n libs** — only import the locales you ship.

### Reduce

1. **Tree-shaking**: ESM imports (`import { foo }`), not CJS (`require('lib')`).
2. **Dead-code-elimination** via Metro's minifier.
3. **Avoid barrel exports** (`index.ts` re-exports everything) — they defeat tree-shake.
4. **Hermes pre-compile**: bytecode is smaller than minified JS in many cases.

## Image Performance (RN)

Images are usually the biggest perf cost on mobile.

### Tools

- **`react-native-fast-image`** — uses SDWebImage (iOS) / Glide (Android). Disk + memory cache. Faster decoding.
- Always `style={{ width, height }}` — fixed dimensions.
- **Resize on the server** (CDN) — never download a 4000px image to a 400px display.
- **WebP** format on both platforms (native support since iOS 14 / Android API 14).

```tsx
import FastImage from 'react-native-fast-image';

<FastImage
  source={{ uri: `https://cdn.app.com/photos/${id}?w=600&fmt=webp`,
            priority: FastImage.priority.normal,
            cache: FastImage.cacheControl.immutable }}
  style={{ width: 200, height: 200 }}
  resizeMode={FastImage.resizeMode.cover}
/>
```

### Image-Heavy Lists

- Pre-fetch images for next-N rows: `FastImage.preload([{ uri: ... }])`.
- Resize / thumbnail on the server; never client-resize a giant image.

## Native Modules — Bridge Cost

Every JS↔native call costs ~50-200µs in the legacy bridge. TurboModules (default in 0.76+ New Architecture) is much faster but still not free.

**Defenses**:

- **Batch calls** — `NativeModule.processMany(items)` instead of N calls.
- **TurboModules** for sync calls when needed (legacy bridge is async-only).
- **JSI** for hot paths — direct C++ binding, near-zero overhead. Use `react-native-mmkv`, `react-native-reanimated`, `react-native-fast-image` patterns.

## Memory + Leaks

### Measure

- **Xcode Instruments → Allocations / Leaks**.
- **Android Studio → Profiler → Memory**.
- **React DevTools profiler** — see what's still mounted that shouldn't be.

### Common Leak Sources

1. **Subscriptions not cleaned up** in `useEffect` return.
2. **Timers** not cleared.
3. **Event listeners** not removed.
4. **Module-scope arrays / maps** that grow forever.
5. **Closures retaining big objects** — captured `data` lives as long as the closure.
6. **Circular refs** in JS (rare; GC handles most).
7. **Native side**: image cache too large, native module retaining buffers.

### Fix

```typescript
useEffect(() => {
  const sub = SomeAPI.subscribe(...);
  const timer = setInterval(...);
  const listener = AppState.addEventListener('change', ...);

  return () => {
    sub.remove();
    clearInterval(timer);
    listener.remove();
  };
}, [...stable deps]);
```

## Battery Drain

The user-visible measure of inefficient code.

**Common drains**:

- Background polls / GPS / Bluetooth that don't pause when app backgrounded.
- WebSocket reconnect storms.
- Repeated wakeups by push notifications without coalescing.
- Long video / audio playback without proper buffering.

**Test**:

- iOS: leave app open 30 min; check Battery section in Settings → Battery for your app's CPU%.
- Android: Battery Historian (`adb bugreport`) or Settings → Battery → Battery usage.

## Per-Phase Tactics

### Pre-launch

- Bundle analyzer run; nothing surprising.
- Hermes + R8/ProGuard enabled.
- FastImage configured.
- Critical screens use FlashList.

### Post-launch monitoring

- Sentry / Crashlytics with performance monitoring (perf traces per screen).
- Real-device cold-start time tracked.
- Bundle size budgeted; CI fails on > 5% growth.

## Source Material

- Callstack — *Ultimate Guide to React Native Optimization*.
- React Native — *Performance Overview*: <https://reactnative.dev/docs/performance>
- Hermes docs — Sampling profiler usage.
- Reanimated 3 docs — worklet patterns.
- Shopify FlashList — internals + optimization guide.
- Apple — *Energy Efficiency Guide for iOS*.
- Android — *Battery and Memory Optimization*.
