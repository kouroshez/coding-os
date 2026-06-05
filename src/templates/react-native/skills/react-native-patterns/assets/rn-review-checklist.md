<!-- domain:MOBILE | layer:asset | ssot:false | updated:2026-06-04 -->
# React Native Review Checklist

Run when building or reviewing a React Native screen/component.

## Lists & rendering
- [ ] Long lists use `FlatList`/`FlashList` (virtualized), never `ScrollView` + `.map`.
- [ ] `keyExtractor` returns a stable id (not index).
- [ ] `renderItem` hoisted + `useCallback`; row is `React.memo`.
- [ ] `FlashList` has `estimatedItemSize`.
- [ ] Styles via `StyleSheet.create` — no inline style objects in render.
- [ ] `python3 scripts/scan_rn_perf.py <screens>` → `clean`.

## Animation & threading
- [ ] Animations use Reanimated worklets (UI thread) or `useNativeDriver: true`.
- [ ] No heavy work on the JS thread during interaction/scroll.

## Architecture (New Architecture / bare RN)
- [ ] TypeScript-side code doesn't leak into native module concerns and vice versa.
- [ ] Platform-specific code isolated (`.ios.tsx`/`.android.tsx` or `Platform.select`).
- [ ] Images sized/cached appropriately (no full-res in a thumbnail).

## Cross-cutting
- [ ] Navigation, offline, push — see mobile-fundamentals.
- [ ] Accessibility labels/roles set — see a11y.
- [ ] `make skills-check-versions` — RN/Expo pins current (where pinned).
