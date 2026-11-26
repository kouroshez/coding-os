# React Native Accessibility Patterns

Concrete patterns for VoiceOver (iOS) + TalkBack (Android) on React Native 0.76+.

## The Five Props You Use Constantly

```tsx
<Pressable
  accessibilityRole="button"          // 'button' | 'link' | 'header' | 'image' | 'text' | 'search' | 'none' | ...
  accessibilityLabel="Save changes"    // primary spoken label
  accessibilityHint="Saves and returns"// secondary, optional
  accessibilityState={{                // disabled | selected | checked | busy | expanded
    disabled: isSaving,
    busy: isSaving,
  }}
  accessibilityValue={{ min: 0, max: 100, now: progress }}
  onPress={handleSave}>
  <Text>Save</Text>
</Pressable>
```

## Hide Decorative Elements

Icons and dividers shouldn't be announced.

```tsx
<View>
  <Image
    source={require('./divider.png')}
    accessibilityElementsHidden={true}                    // iOS
    importantForAccessibility="no-hide-descendants"      // Android
    accessible={false}
  />
  <Text>Content</Text>
</View>
```

For an `<Icon>` paired with text:

```tsx
{/* The icon is decorative; the text label is enough */}
<Pressable accessibilityRole="button" accessibilityLabel="Notifications">
  <Icon name="bell" accessible={false} />
</Pressable>

{/* The icon IS the button */}
<Pressable accessibilityRole="button" accessibilityLabel="Open notifications">
  <Icon name="bell" accessible={false} />
</Pressable>
```

## Group Related Elements

```tsx
{/* SR reads "Lesson: Hexagons. 3 of 10 completed." as one unit */}
<View
  accessible={true}
  accessibilityLabel={`Lesson: ${lesson.title}. ${lesson.completed} of ${lesson.total} completed.`}>
  <Text>{lesson.title}</Text>
  <Text>{lesson.completed} of {lesson.total} completed</Text>
</View>
```

Without `accessible={true}`, SR reads each child separately — slower, less coherent.

## Headers — Navigation by Heading

VoiceOver / TalkBack let users jump heading-to-heading. Mark them.

```tsx
<Text accessibilityRole="header" style={styles.title}>
  Profile
</Text>

<Text accessibilityRole="header" accessibilityLevel={2} style={styles.section}>
  Account
</Text>
```

Use `accessibilityLevel` (1-6) when meaningful; defaults to 1.

## Screen-Reader-Only Text

Sometimes you want extra info ONLY for SR (not visible). Use a visually-hidden Text:

```tsx
<Pressable accessibilityRole="button">
  <Icon name="trash" accessible={false} />
  <Text style={visuallyHidden}>Delete this lesson</Text>
</Pressable>

const visuallyHidden = {
  position: 'absolute' as const,
  width: 1, height: 1,
  overflow: 'hidden' as const,
};
```

## Live Region (Status Updates)

```tsx
const [status, setStatus] = useState('');

<View
  accessible={true}
  accessibilityLiveRegion="polite">       // Android only; iOS uses announce
  <Text>{status}</Text>
</View>

// Cross-platform announce:
import { AccessibilityInfo } from 'react-native';
AccessibilityInfo.announceForAccessibility('Saved successfully');
```

`AccessibilityInfo.announceForAccessibility(...)` works on both platforms, doesn't move focus, doesn't interrupt unless very recent.

## Forms

```tsx
<View>
  <Text accessibilityRole="header">Sign In</Text>

  {/* Label is rendered + tied via accessibilityLabel */}
  <Text>Email</Text>
  <TextInput
    accessibilityLabel="Email address"
    autoComplete="email"
    autoCapitalize="none"
    keyboardType="email-address"
    returnKeyType="next"
    value={email}
    onChangeText={setEmail}
  />
  {emailError && (
    <Text
      accessibilityLiveRegion="polite"
      accessibilityRole="alert"
      style={styles.errorText}>
      {emailError}
    </Text>
  )}

  <Text>Password</Text>
  <TextInput
    accessibilityLabel="Password"
    autoComplete="current-password"
    secureTextEntry
    returnKeyType="done"
    value={password}
    onChangeText={setPassword}
    onSubmitEditing={handleSubmit}
  />

  <Pressable
    accessibilityRole="button"
    accessibilityLabel="Sign in"
    accessibilityState={{ disabled: isSubmitting, busy: isSubmitting }}
    onPress={handleSubmit}
    disabled={isSubmitting}>
    <Text>{isSubmitting ? 'Signing in…' : 'Sign in'}</Text>
  </Pressable>
</View>
```

`autoComplete` matters: `email`, `username`, `current-password`, `new-password`, `name`, `tel`, `street-address`, `cc-number`, `one-time-code` (for SMS OTP autofill), `birthdate-full`.

## Modal — Focus Trap + Initial Focus

RN modals via React Navigation:

```tsx
<Stack.Screen
  name="ConfirmDelete"
  component={ConfirmDeleteScreen}
  options={{
    presentation: 'modal',
    headerTitle: 'Confirm delete',
    headerBackAccessibilityLabel: 'Cancel',
  }}
/>
```

Inside the modal, focus the primary button on mount + announce purpose:

```tsx
import { useEffect, useRef } from 'react';
import { AccessibilityInfo, findNodeHandle, View } from 'react-native';

export function ConfirmDeleteScreen() {
  const titleRef = useRef<View>(null);

  useEffect(() => {
    requestAnimationFrame(() => {
      const tag = findNodeHandle(titleRef.current);
      if (tag) AccessibilityInfo.setAccessibilityFocus(tag);
    });
    AccessibilityInfo.announceForAccessibility('Confirm delete');
  }, []);

  return (
    <View>
      <Text accessibilityRole="header" ref={titleRef}>Confirm delete</Text>
      <Text>This action cannot be undone.</Text>
      <Pressable accessibilityRole="button" accessibilityLabel="Cancel" onPress={cancel}>
        <Text>Cancel</Text>
      </Pressable>
      <Pressable accessibilityRole="button" accessibilityLabel="Delete permanently" onPress={confirm}>
        <Text>Delete</Text>
      </Pressable>
    </View>
  );
}
```

Native modals from React Navigation handle focus return on dismiss automatically.

## Touch Targets

WCAG 2.5.8: minimum 24×24 CSS px. iOS HIG recommends 44×44pt. Android Material recommends 48×48dp.

```tsx
<Pressable
  hitSlop={{ top: 12, right: 12, bottom: 12, left: 12 }}    // expand effective tap area
  style={styles.icon}>
  <Icon name="close" size={20} />
</Pressable>
```

`hitSlop` is the pragmatic answer when the visible icon is small but the touch area should be larger.

## Long Lists — FlashList Accessibility

FlashList recycles rows. Each cell needs explicit accessibility props or SR may read the wrong content.

```tsx
<FlashList
  data={lessons}
  estimatedItemSize={88}
  renderItem={({ item }) => (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${item.title}, ${item.completed ? 'completed' : 'not started'}`}
      onPress={() => navigate('Lesson', { lessonId: item.id })}>
      <Text>{item.title}</Text>
    </Pressable>
  )}
  keyExtractor={(item) => item.id}
/>
```

## Dynamic Type

iOS users can scale text up to ~310% via Settings → Accessibility → Display & Text Size. RN's `<Text>` respects this by default (`allowFontScaling={true}`).

```tsx
{/* Default: scales with user setting */}
<Text style={{ fontSize: 16 }}>Body</Text>

{/* OPT OUT (rare — only for fixed UI like number-pad keys) */}
<Text style={{ fontSize: 16 }} allowFontScaling={false}>1</Text>

{/* Cap the scale to avoid layout breakage */}
<Text style={{ fontSize: 16 }} maxFontSizeMultiplier={1.6}>...</Text>
```

Test at the largest accessibility setting (`AX5`). Fix layout breakage by allowing wrap, scrollable containers, conditional element hiding.

## Reduce Motion

```tsx
import { AccessibilityInfo } from 'react-native';

const [reduceMotion, setReduceMotion] = useState(false);
useEffect(() => {
  AccessibilityInfo.isReduceMotionEnabled().then(setReduceMotion);
  const sub = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduceMotion);
  return () => sub.remove();
}, []);

// Use in animations:
const transition = reduceMotion ? withTiming(target, { duration: 0 })
                                : withSpring(target);
```

Reanimated 3 worklets respect this if you check inside the worklet.

## Color + Dark Mode

`useColorScheme()` returns 'light' | 'dark' from system pref.

```tsx
import { useColorScheme } from 'react-native';

const scheme = useColorScheme();
const styles = scheme === 'dark' ? darkStyles : lightStyles;
```

Verify contrast in BOTH modes — colors that pass AA on white may fail on near-black.

## Testing — Per Flow

Run through each critical flow with VoiceOver / TalkBack on:

- **Sign-in**: focus reaches each field, errors announced, success navigates correctly.
- **Browse → start lesson**: list announces title + status, can tap to open.
- **Settings**: every toggle / button reachable + correctly labeled.
- **Modal**: opens with focus on title, Esc / back button closes, focus restored.
- **Form**: required fields announced, errors announced, submit works.

For automated checks: add `@testing-library/react-native` accessibility queries to component tests.

```typescript
import { render, screen } from '@testing-library/react-native';

test('save button has accessible label', () => {
  render(<SaveButton />);
  const button = screen.getByRole('button', { name: 'Save changes' });
  expect(button).toBeOnTheScreen();
});
```

## Common RN a11y Failures

1. **`<View onPress>`** instead of `<Pressable>` — no role, no SR feedback.
2. **Icon button without `accessibilityLabel`** — SR reads nothing.
3. **`accessibilityRole` not set** on custom-styled Pressable — SR doesn't know it's a button.
4. **Decorative image not hidden** — SR reads "image" with no value.
5. **Text in nested Pressable + Text not grouped** — SR reads each separately.
6. **`accessibilityLabel` doesn't include state** — "Save" instead of "Save, disabled".
7. **Modal opens, focus stays on the trigger** — SR user lost.
8. **No `setAccessibilityFocus` after route change** — same.
9. **Scroll target not focused after auto-scroll** — SR doesn't follow scroll.
10. **Long async load with no announcement** — user thinks app froze.
11. **`maxFontSizeMultiplier` not set on tight UI** — Dynamic Type breaks layout.
12. **Color-only state (selected tab, error)** — color blind users miss it.

## Source Material

- React Native — *Accessibility*: <https://reactnative.dev/docs/accessibility>
- Apple — *Accessibility on iOS*: <https://developer.apple.com/accessibility/>
- Android — *Accessibility*: <https://developer.android.com/guide/topics/ui/accessibility>
- Callstack — *Accessible mobile apps* blog series.
- Shopify FlashList docs — recycler-aware accessibility patterns.
