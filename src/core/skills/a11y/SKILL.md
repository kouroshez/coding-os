---
name: a11y
description: Accessibility (a11y) for web + mobile per WCAG 2.2 AA. Use when writing or reviewing UI code (React, React Native, Vue, Svelte) — screens, components, forms, modals, toasts, navigation. Covers semantic HTML / RN AccessibilityInfo props, ARIA patterns (use natives first), keyboard navigation, focus management, screen reader testing (VoiceOver / TalkBack / NVDA), color contrast, motion sensitivity, accessible forms with error handling, live regions, automated tooling (axe-core, Lighthouse, Playwright). Pairs with frontend-fundamentals (generic UI patterns).
last_reviewed: "2026-05-11"

---

# Accessibility — WCAG 2.2 AA

A practical playbook for making UI usable by people with disabilities. WCAG 2.2 (October 2023, current standard) at AA level is the legal compliance bar in most jurisdictions and the right minimum for any app shipping in 2026.

## When to Use This Skill

- Writing or reviewing any screen / component / form / modal.
- Adding interactive UI (buttons, menus, dropdowns, tabs).
- Setting up navigation (skip links, focus trap in modals).
- Choosing colors / typography for the design system.
- Auditing the app before launch.
- Responding to accessibility user feedback / lawsuit risk assessment.

For the cross-platform mobile concerns, see `mobile-fundamentals`. For component patterns, see `react-native-patterns` (RN) or `frontend-fundamentals` (web).

## The Four POUR Principles (WCAG)

WCAG organizes everything around four principles. Memorize the acronym; it's the lens for every UI decision.

1. **Perceivable** — Users must be able to perceive the content. Text alternatives for images, captions for video, sufficient color contrast, no info conveyed by color alone.
2. **Operable** — Users must be able to operate the UI. Keyboard accessible, enough time, no seizure-inducing flashes, navigable.
3. **Understandable** — Users must be able to understand the content + UI. Readable language, predictable behavior, helpful error messages.
4. **Robust** — Content works with current AND future assistive tech. Semantic markup, valid code, ARIA used correctly.

## Use Native Elements First

The most common a11y mistake: rebuilding a `<button>` as `<div onClick>`. The native element ships with:

- Keyboard accessibility (Enter/Space to activate).
- Focus indicator (browser default).
- Role announcement to screen readers ("button").
- Disabled state semantics.
- Form integration (submit, reset).

```html
<!-- WRONG — div + onClick. Loses everything. -->
<div onClick={handleClick}>Save</div>

<!-- RIGHT -->
<button type="button" onClick={handleClick}>Save</button>
```

```tsx
{/* React Native — use Pressable, not View + onPress */}
<Pressable
  accessibilityRole="button"
  accessibilityLabel="Save changes"
  onPress={handlePress}>
  <Text>Save</Text>
</Pressable>
```

ARIA exists to fill gaps where native doesn't cover the pattern. The first rule of ARIA: don't use ARIA. The second rule: if you must, copy the pattern from the W3C ARIA Authoring Practices Guide (APG) — don't invent.

## Color + Contrast (WCAG 1.4.3, 1.4.11)

| Content | Minimum contrast ratio (AA) | Better (AAA) |
|---|---|---|
| Body text (< 18pt) | **4.5 : 1** | 7 : 1 |
| Large text (≥ 18pt or 14pt bold) | **3 : 1** | 4.5 : 1 |
| UI components, graphics (1.4.11) | **3 : 1** | n/a |

Tools:

- **Browser DevTools** — color picker shows contrast ratio inline.
- **Stark** (Figma plugin) — design-time check.
- **axe DevTools** (Chrome extension) — runtime audit.

**Don't convey info by color alone** (1.4.1). A red border for "error" is fine, but pair with an icon + text. Color-blind users won't see the red.

## Typography

- **Minimum body size**: 16px on web; the platform default on mobile.
- **Line height**: ≥ 1.5 (WCAG 1.4.12).
- **Letter spacing**: ≥ 0.12em for body text.
- **Don't disable user zoom** on mobile (`maximum-scale=1.0` in viewport meta is an a11y violation).
- **RN: support Dynamic Type** — text uses `allowFontScaling={true}` (default); test at the largest accessibility setting.

## Keyboard Navigation (WCAG 2.1)

Every interactive element must be reachable + operable via keyboard alone.

- **Tab order matches visual order** — DOM order is the default; avoid `tabindex` > 0.
- **Visible focus indicator** — never `outline: none` without a replacement. Use a 2-3px outline OR `:focus-visible` for keyboard-only focus.
- **Skip link** at the top of the page: "Skip to main content" — visible on focus.
- **No keyboard traps** — user can always Tab/Esc out.
- **Custom widgets** (autocomplete, tabs, accordion) — implement keyboard interactions per W3C ARIA APG patterns.

```css
/* Good visible focus */
button:focus-visible,
a:focus-visible,
[role="button"]:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
}

/* Skip link */
.skip-link {
  position: absolute;
  left: -9999px;
}
.skip-link:focus {
  left: 1rem;
  top: 1rem;
  z-index: 100;
}
```

## Focus Management (WCAG 2.4.3, 3.2.2)

When the UI changes, move focus deliberately:

- **Modal opens** → focus first interactive element. Esc closes. Focus restored on close.
- **Route change** → focus the new page's `<h1>` (or main landmark). Screen reader re-announces.
- **Form submit error** → focus the first invalid field (or the error summary).
- **Toast / alert appears** → use `role="status"` (polite) or `role="alert"` (assertive) — DON'T move focus unless interaction is required.

For the full focus-trap implementation in React + RN, see [references/aria-and-focus.md](references/aria-and-focus.md).

## Forms — Get These Right or You Lose Users

Most accessibility failures are in forms. The fixes are simple:

1. **Every input has a `<label>`** — or `aria-label` / `aria-labelledby` if visually hidden.
2. **`htmlFor` matches `id`** so clicking the label focuses the input.
3. **`required` attribute** + `aria-required="true"` (some screen readers don't announce HTML required).
4. **Inline errors** with `aria-describedby` pointing to the error message + `aria-invalid="true"` on the input.
5. **Submit error summary** at the top — `role="alert"`, focusable, links to each invalid field.
6. **`autocomplete` attribute** for known fields (`name`, `email`, `tel`, `street-address`, `cc-number`, `current-password`, `new-password`, `one-time-code`).
7. **Group related fields** with `<fieldset>` + `<legend>`.

```tsx
<label htmlFor="email">Email</label>
<input
  id="email"
  type="email"
  required
  aria-required="true"
  autoComplete="email"
  aria-invalid={!!errors.email}
  aria-describedby={errors.email ? 'email-error' : undefined}
  {...register('email')}
/>
{errors.email && (
  <span id="email-error" role="alert">{errors.email.message}</span>
)}
```

## React Native — AccessibilityInfo Props

RN uses `accessibility*` props on every component. The minimum:

```tsx
<Pressable
  accessibilityRole="button"          // button | link | header | image | text | search | ...
  accessibilityLabel="Save changes"   // what VoiceOver/TalkBack announces
  accessibilityHint="Saves the form and returns to the previous screen"  // optional secondary
  accessibilityState={{ disabled: isSaving }}
  onPress={handleSave}>
  <Text>Save</Text>
</Pressable>
```

Other essentials:

- **`accessibilityRole`** for non-`<Text>`/`<Pressable>` containers (header, list, none).
- **`accessibilityLabel`** for icons and image-only buttons (otherwise SR reads nothing).
- **`accessibilityElementsHidden={true}`** + **`importantForAccessibility="no-hide-descendants"`** to hide decorative views.
- **`accessibilityLiveRegion="polite"`** (Android) / RN `AccessibilityInfo.announceForAccessibility(...)` (iOS) — for status updates.

For the full RN-specific patterns including FlashList / form / modal / focus management, see [references/rn-accessibility.md](references/rn-accessibility.md).

## Motion + Animation (WCAG 2.3.3)

Some users get motion sickness from parallax, slide transitions, autoplay video. Respect `prefers-reduced-motion`.

```css
/* Disable transitions for users who request reduced motion */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

```tsx
// React Native
import { AccessibilityInfo } from 'react-native';

const [reduceMotion, setReduceMotion] = useState(false);
useEffect(() => {
  AccessibilityInfo.isReduceMotionEnabled().then(setReduceMotion);
  const sub = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduceMotion);
  return () => sub.remove();
}, []);

// Then conditionally:
const transition = reduceMotion ? { duration: 0 } : { duration: 250 };
```

Auto-play video: must have a way to pause/stop within 5 seconds (WCAG 2.2.2).

## Screen Reader Testing — How

You MUST test with a screen reader. Reading WCAG isn't enough.

| Platform | Screen reader | Activation |
|---|---|---|
| macOS | VoiceOver | Cmd+F5 |
| Windows | NVDA (free) | Ctrl+Alt+N after install |
| iOS | VoiceOver | Settings → Accessibility → VoiceOver → On (or triple-press home/side) |
| Android | TalkBack | Settings → Accessibility → TalkBack → On |
| Chrome (dev) | ChromeVox | Extension |

Test the critical flows: sign-in, add-to-cart / start-lesson, checkout / pay, settings, sign-out. If you can complete each flow eyes-closed using only the screen reader, the app is in good shape.

For the testing protocol + per-flow checklist, see [references/screen-reader-testing.md](references/screen-reader-testing.md).

## Automated Tooling

Catch the easy wins automatically. None of these replace manual testing.

- **axe-core** — runs in browser DevTools, in Playwright tests, in CI. The most thorough automated audit available.
- **Lighthouse** — built into Chrome; lower fidelity than axe but gives a score.
- **eslint-plugin-jsx-a11y** — catches anti-patterns at lint time (img without alt, click handler on non-interactive).
- **eslint-plugin-react-native-a11y** — RN-specific lint rules.
- **Playwright + @axe-core/playwright** — `await new AxeBuilder({ page }).analyze()` per critical page in CI.
- **react-axe / @axe-core/react** — runs axe on every render in dev mode.

```typescript
// Playwright a11y test in CI
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('home page is accessible', async ({ page }) => {
  await page.goto('/');
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
```

Fail the build on serious + critical violations.

## Common a11y Failures (and Fixes)

1. **`<div onClick>` instead of `<button>`** — use button.
2. **Color-only error indicator** — add icon + text.
3. **Missing alt on image** — `<img alt="...">` (or `alt=""` for decorative).
4. **Modal opens, focus stays elsewhere** — focus first input on open.
5. **Modal closes, focus disappears** — restore to the trigger.
6. **No keyboard support for custom widget** — implement per ARIA APG.
7. **Form input without label** — every input gets a `<label>`.
8. **Error message only visible (not announced)** — use `aria-describedby` or `role="alert"`.
9. **`outline: none`** — replace with `:focus-visible` styles.
10. **`maximum-scale=1.0`** in viewport — remove.
11. **Auto-play video / parallax without `prefers-reduced-motion`** — gate it.
12. **Tab order doesn't match visual** — fix DOM order; avoid `tabindex>0`.
13. **`tabindex="-1"` on something users need to reach** — remove.
14. **Decorative icon without `aria-hidden="true"`** — SR reads "image".
15. **RN button without `accessibilityLabel`** — SR reads nothing useful.
16. **No skip link** — keyboard users tab through nav on every page.
17. **Insufficient touch target** — WCAG 2.5.8 says min 24×24 CSS px (mobile usually wants 44×44).
18. **No language attribute** on `<html>` — set `<html lang="en">`.
19. **Page title same on every route** — set per page (`<title>` on web, `accessibilityViewIsModal` + announce on RN).

## WCAG 2.2 — New AA Criteria (vs 2.1)

WCAG 2.2 added 6 success criteria worth knowing:

- **2.4.11 Focus Not Obscured (Min)** — focused element NOT entirely hidden by sticky header / cookie banner.
- **2.4.12 Focus Not Obscured (Enh.)** — AAA — fully visible.
- **2.5.7 Dragging Movements** — every drag has a non-drag alternative (e.g., re-order list also via long-press menu).
- **2.5.8 Target Size (Minimum)** — 24×24 CSS px minimum (mobile patterns + density permitting).
- **3.2.6 Consistent Help** — help link in same place across pages.
- **3.3.7 Redundant Entry** — autofill prior info; don't make user re-type.
- **3.3.8 Accessible Authentication** — no "type 4 random characters from your password" puzzles.
- **3.3.9 Accessible Authentication (Enh.)** — AAA.

Most apps already do these; check explicitly.

## Pre-Launch a11y Checklist

See [assets/a11y-checklist.md](assets/a11y-checklist.md). Each item is a concrete check; uncheck → fix or document waiver.

## Source Material

- *WCAG 2.2*: <https://www.w3.org/TR/WCAG22/>
- *ARIA Authoring Practices Guide (APG)*: <https://www.w3.org/WAI/ARIA/apg/> — copy-paste patterns for combobox, tabs, etc.
- *WebAIM*: <https://webaim.org/> — practical articles + free contrast checker.
- *Inclusive Components* (Heydon Pickering) — book + blog with deep component patterns.
- *axe-core docs*: <https://github.com/dequelabs/axe-core>
- *Apple HIG — Accessibility*: <https://developer.apple.com/design/human-interface-guidelines/accessibility>
- *Android Accessibility*: <https://developer.android.com/guide/topics/ui/accessibility>
