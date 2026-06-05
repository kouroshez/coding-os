<!-- domain:MOBILE | layer:asset | ssot:false | updated:2026-06-04 -->
# React Native (Bare/Expo) Review Checklist

Run when starting, upgrading, or reviewing a React Native app.

## Baseline
- [ ] New Architecture (Fabric + TurboModules) on; Hermes engine on.
- [ ] React Navigation 7 native-stack; param lists typed.
- [ ] Expo (prebuild for native) unless a hard native requirement justifies bare.
- [ ] `make skills-check-versions` — RN/Expo pins current.

## Upgrade safety
- [ ] Every third-party native lib supports the New Architecture before bumping.
- [ ] Test on both iOS + Android (real devices/emulators), not one.

## Quality (with react-native-patterns)
- [ ] Lists virtualized (FlatList/FlashList), stable keys, memoized rows.
- [ ] Reanimated worklets for interactive animation (UI thread).
- [ ] Platform-specific code isolated (`.ios`/`.android` or `Platform.select`).
- [ ] Accessibility labels/roles set (a11y).

## Cross-cutting (mobile-fundamentals)
- [ ] Navigation, deep links, push, offline-sync handled per mobile-fundamentals.
- [ ] Secure storage for tokens (Keychain/Keystore) — security-mobile.

## Release
- [ ] EAS Update (OTA) for JS-only fixes; store build for native changes.
- [ ] Maestro flow covers the core journey (end-to-end-testing).
