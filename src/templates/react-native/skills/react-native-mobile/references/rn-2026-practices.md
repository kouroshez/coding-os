<!-- domain:MOBILE | layer:reference | ssot:true | updated:2026-06-04 -->
# React Native Practices (2026) — New Architecture, Hermes, Expo

> P: The current RN baseline (New Architecture default, Hermes, Expo SDK 56) and what it changes.
> R: Starting or upgrading a React Native app; choosing bare vs Expo.
> S: List/render performance — that's the react-native-patterns skill's list-performance reference.
> N: [SKILL.md](../SKILL.md), [rn-mobile-checklist.md](../assets/rn-mobile-checklist.md)

> Nav: [Skill](../SKILL.md)

Baseline as of 2026: React Native 0.85.x, React 19.2, Hermes (V1) default, the
**New Architecture** (Fabric + TurboModules + JSI) default. Expo SDK 56 wraps
this. Pins in [versions.json](../versions.json).

## Expo vs bare — pick deliberately

| | Expo (managed/prebuild) | Bare RN |
|---|---|---|
| native modules | config plugins + prebuild | edit ios/android directly |
| OTA updates | EAS Update built-in | roll your own |
| build | EAS Build (cloud) | local Xcode/Gradle |
| use when | most apps — faster, less native pain | deep native customization needed |

Default to Expo (with prebuild for native modules) unless you have a hard native
requirement — it removes most of the iOS/Android toolchain pain. Cross-platform
concerns (push, deep links, offline) are owned by
[mobile-fundamentals](../../../core/skills/mobile-fundamentals/SKILL.md).

## New Architecture implications

- **TurboModules** — native modules load lazily via JSI (no bridge serialization);
  faster startup. Codegen from a TS spec defines the native interface.
- **Fabric** — the new renderer; concurrent-React-friendly, synchronous layout
  reads when needed. Most app code doesn't change, but old native UI libraries may
  need a Fabric-compatible version.
- When upgrading, the long pole is third-party native libraries — check each
  supports the New Architecture before bumping.

## Navigation, gestures, animation

- **React Navigation 7** — native-stack (uses platform navigators) for native feel
  and performance; type the param lists.
- **Reanimated 3** + **Gesture Handler** — animations/gestures run on the UI
  thread (worklets), so a busy JS thread won't drop them. Prefer to the legacy
  `Animated` API for anything interactive.
- **FlashList** (Shopify) over `FlatList` for large lists.

## Quality + release

Hermes gives faster startup + lower memory — keep it on. Profile with the React
DevTools profiler / Flipper / `react-native-performance`. Ship via EAS (Expo) or
Fastlane (bare); use OTA updates (EAS Update) for JS-only fixes, a store build for
native changes. Test journeys with Maestro
([end-to-end-testing](../../../core/skills/end-to-end-testing/SKILL.md)).
