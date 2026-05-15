<!-- domain:REACTNATIVE | layer:reference | ssot:true | updated:2026-04-29 -->
# Mobile Accessibility (a11y) Checklist — WCAG 2.2 AA

> P: Per-screen / per-component a11y bar for every `src/mobile/**/*.{ts,tsx}` change. Tests with VoiceOver (iOS) AND TalkBack (Android).
> R: Reviewing or writing any interactive RN component.
> S: Touching pure backend / sync code with no UI surface.
> N: [mobile-rules.md](mobile-rules.md), [offline-first.md](offline-first.md), [../playbooks/mobile-app.md](../playbooks/mobile-app.md)

> Nav: [Docs Index](../00-index.md) | [Mobile Rules](./mobile-rules.md)

---

## 1. Interactive elements

- Every `Pressable` / `TouchableOpacity` / `Button` / icon-only tap target MUST set:
  - `accessibilityRole` (`button` | `link` | `tab` | `header` | …)
  - `accessibilityLabel` describing the action (no emoji-only labels)
  - `accessibilityState` for stateful elements (`{ disabled, selected, checked, expanded }`)
- Tap targets MUST be ≥ 44×44 pt (iOS) / 48×48 dp (Android). Smaller surfaces wrap a larger `hitSlop`.
- Form fields MUST set `accessibilityLabel` when no visible label is present.

## 2. Dynamic announcements

- Use `AccessibilityInfo.announceForAccessibility(message)` for:
  - Toast / banner-style state changes that have no visible focus.
  - Async result toasts (sync queue success / failure).
- Live-region updates use `accessibilityLiveRegion="polite"` (Android) plus an explicit announce on iOS.
- Never auto-focus an element on screen mount unless it materially helps a screen-reader user.

## 3. Navigation + focus

- Use `accessibilityFocus()` on screen change ONLY when the user benefits — e.g. error recovery, modal open.
- Tab order follows visual reading order; never reorder via `accessibilityElementsHidden` for layout reasons.
- Modal-equivalent surfaces (`Modal`, bottom sheets) MUST set `accessibilityViewIsModal` (iOS) and trap focus.
- Provide a clear close affordance with `accessibilityLabel="Close"`.

## 4. Color + contrast

- Normal text (< 18 sp): contrast ratio ≥ 4.5:1.
- Large text (≥ 18 sp bold or ≥ 24 sp): ≥ 3:1.
- Interactive elements vs adjacent surfaces: ≥ 3:1.
- Focus / selection indicators: ≥ 3:1 against background.
- Theme-tested in both light AND dark modes.

## 5. Motion + animation

- Respect `useReduceMotion()` from `react-native-reanimated`. Disable parallax / hero animations when on.
- Auto-playing motion ≤ 5 s OR provide a pause control.
- Avoid flashing content > 3 Hz (seizure trigger).

## 6. Text + scaling

- Read user's font scale via `Appearance` / `PixelRatio.getFontScale()`. Layouts MUST tolerate up to 200%.
- Never set fixed heights on rows containing text — use min-height plus content-driven growth.
- Avoid `numberOfLines` clipping on critical info; prefer expandable sections.

## 7. Images + media

- All images carry `accessibilityLabel` OR `accessibilityRole="image"` with descriptive `alt`-equivalent.
- Decorative-only images: `accessible={false}` AND `importantForAccessibility="no"`.
- Video content carries captions OR a textual alternative.

## 8. Forms

- Labels associated to inputs via `accessibilityLabelledBy` (Android) / `accessibilityLabel` fallback.
- Error messages use `accessibilityLiveRegion="assertive"` (Android) + announceForAccessibility (iOS).
- Required fields announce required state.

## 9. Test discipline

- Manual: run every changed screen through VoiceOver AND TalkBack before merge.
- Automated: `axe-core/react-native` in unit tests for component-level a11y.
- E2E: Maestro flow uses `accessibilityLabel` selectors so a broken label fails the flow loudly.

## 10. Reference table

| Concern | iOS prop | Android prop |
|---|---|---|
| Role | `accessibilityRole` | `accessibilityRole` |
| Label | `accessibilityLabel` | `accessibilityLabel` |
| State | `accessibilityState` | `accessibilityState` |
| Hint | `accessibilityHint` | `accessibilityHint` |
| Live region | `accessibilityLiveRegion` (no-op) | `accessibilityLiveRegion` |
| Modal | `accessibilityViewIsModal` | (focus trap manual) |
| Hide from reader | `accessibilityElementsHidden` | `importantForAccessibility="no"` |

## 11. Pre-merge checklist

- [ ] Every interactive element has role + label + state where applicable.
- [ ] Tap target ≥ 44×44 pt / 48×48 dp.
- [ ] Color contrast verified (light + dark).
- [ ] Reduce-motion respected.
- [ ] VoiceOver smoke pass.
- [ ] TalkBack smoke pass.
- [ ] axe-core tests green.
