<!-- domain:MOBILE | layer:reference | ssot:true | updated:2026-06-04 -->
# React Native List & Render Performance

> P: Keep scroll at 60fps and avoid the re-render cascades that make RN feel slow.
> R: Building any list screen or a component that re-renders often.
> S: Cross-platform mobile concerns (navigation, offline) — that's mobile-fundamentals.
> N: [SKILL.md](../SKILL.md), [rn-review-checklist.md](../assets/rn-review-checklist.md)

> Nav: [Skill](../SKILL.md)

## Never ScrollView a long list

```tsx
// Wrong — renders ALL items up front; janky + memory-heavy
<ScrollView>{items.map((i) => <Row key={i.id} item={i} />)}</ScrollView>

// Correct — virtualized: renders only what's visible
<FlatList data={items} keyExtractor={(i) => i.id} renderItem={renderRow} />
```

`ScrollView` mounts every child; `FlatList` (or Shopify `FlashList`, faster)
virtualizes. `FlashList` needs an `estimatedItemSize` and recycles views — prefer
it for large/heterogeneous lists.

## Stable renderItem + keyExtractor

```tsx
// Wrong — new function identity each render defeats memoization
<FlatList renderItem={({ item }) => <Row item={item} />} />

// Correct — hoisted, memoized item
const Row = React.memo(({ item }) => <Text>{item.name}</Text>);
const renderRow = useCallback(({ item }) => <Row item={item} />, []);
<FlatList data={data} keyExtractor={(i) => i.id} renderItem={renderRow} />
```

`React.memo` the row, `useCallback` the renderItem, and give a real
`keyExtractor` — without it RN uses array index keys and re-renders on reorder.
`scan_rn_perf.py` flags inline renderItem, missing keyExtractor, and inline styles.

## StyleSheet, not inline objects

```tsx
// Wrong — new style object every render
<View style={{ padding: 16 }} />

// Correct — created once
const styles = StyleSheet.create({ box: { padding: 16 } });
<View style={styles.box} />
```

`StyleSheet.create` returns stable references (and historically an id passed over
the bridge). Inline style objects are a fresh reference each render → the child
re-renders.

## Animations on the UI thread (Reanimated)

Run animations with **Reanimated** worklets so they execute on the UI thread, not
the JS thread — a busy JS thread won't drop the animation. `useSharedValue` +
`useAnimatedStyle` keep the frame loop off JS. The old `Animated` API with
`useNativeDriver: true` covers transform/opacity; layout-driving animation needs
Reanimated.

## Diagnose

Hermes is the default engine (faster startup, less memory). Profile with Flipper /
the React DevTools profiler / `react-native-performance`; watch for: long lists
without virtualization, components re-rendering on unrelated state, large images
not resized, and bridge chatter (batch native calls). Measure before optimizing —
the slow thing is often not where you guess.
