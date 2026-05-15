# Accessibility Pre-Launch Checklist (WCAG 2.2 AA)

Run before each release. Each item is a concrete check; uncheck → fix or document waiver with reason + ETA.

## Semantic Structure

- [ ] Single `<h1>` per page; nested headings (h1 > h2 > h3) without skipping levels.
- [ ] Landmark regions used (`<header>`, `<nav>`, `<main>`, `<footer>`, `<aside>`) on web.
- [ ] React Native: `accessibilityRole="header"` on titles; `accessibilityRole="button"` on Pressables; `accessibilityRole="link"` on cross-app links.
- [ ] Lists use `<ul>` / `<ol>`; nav menus use `<nav>` + `<ul>`.
- [ ] No `<div onClick>` instead of `<button>` / `<Pressable>`.

## Keyboard

- [ ] Every interactive element reachable via Tab.
- [ ] Tab order matches visual order.
- [ ] No keyboard traps (can always Tab/Esc out).
- [ ] Visible focus indicator on all focusable elements.
- [ ] Skip link to main content (web).
- [ ] Custom widgets (combobox, tabs, menu) follow ARIA APG keyboard pattern.
- [ ] Modal traps focus; Esc closes; focus restored on close.
- [ ] Touch target ≥ 24×24 CSS px (WCAG 2.5.8); mobile typically 44×44.

## Color + Contrast

- [ ] Body text contrast ≥ 4.5:1 on every background it appears on.
- [ ] Large text (≥18pt or 14pt bold) ≥ 3:1.
- [ ] UI components + meaningful graphics ≥ 3:1.
- [ ] Focus indicator ≥ 3:1 against surrounding background.
- [ ] No info conveyed by color alone (every red border has an icon + text).
- [ ] Dark mode AND light mode both pass contrast checks.

## Forms

- [ ] Every input has a visible `<label>` or `accessibilityLabel`.
- [ ] `htmlFor` matches `id`; clicking label focuses input.
- [ ] `required` + `aria-required="true"` on required fields.
- [ ] `autoComplete` set on known fields (`email`, `current-password`, `new-password`, `name`, `tel`, `street-address`, `cc-number`, `one-time-code`).
- [ ] Inline error message: `aria-describedby` on input, `aria-invalid="true"`, `role="alert"` on the error.
- [ ] Submit error: focus first invalid field OR error summary at top.
- [ ] Field grouping with `<fieldset>` + `<legend>` where appropriate.
- [ ] No CAPTCHAs without an accessible alternative (audio CAPTCHA / reCAPTCHA v3 / passkey).

## Images + Media

- [ ] Every `<img>` has `alt=""` (decorative) or descriptive `alt="..."`.
- [ ] React Native `<Image>` decorative: `accessible={false}` + `accessibilityElementsHidden={true}`.
- [ ] `<Image>` informative: `accessibilityLabel="..."`.
- [ ] Video has captions OR is decorative + auto-pauses within 5 sec.
- [ ] Audio has transcripts.
- [ ] No autoplay video / audio (or muted + ≤ 5 sec).

## Motion + Animation

- [ ] `prefers-reduced-motion` media query respected (web).
- [ ] React Native: check `AccessibilityInfo.isReduceMotionEnabled()` and disable / shorten animations.
- [ ] No flashing > 3 times per second (seizure trigger).
- [ ] Parallax / auto-scroll has stop control.

## Modals + Dialogs

- [ ] Use native `<dialog>` (web) or React Navigation modal preset (RN).
- [ ] Focus moves to first interactive (or dialog itself) on open.
- [ ] Focus trap inside; Esc / back button closes.
- [ ] Focus returns to trigger on close.
- [ ] `aria-labelledby` or `accessibilityLabel` on the dialog.
- [ ] Backdrop click dismisses (or has documented reason not to).

## Navigation

- [ ] Page title set per route (`<title>` on web; React Navigation `headerTitle` or `accessibilityViewIsModal` + `announceForAccessibility` on RN).
- [ ] Skip link at top (web).
- [ ] Active nav item visually + programmatically marked (`aria-current="page"` or `accessibilityState={{ selected: true }}`).
- [ ] Breadcrumb navigation (when used) marked with `aria-label="Breadcrumb"`.

## Live Regions / Status

- [ ] Async loading announced: `role="status"` (web) / `accessibilityLiveRegion="polite"` + `announceForAccessibility` (RN).
- [ ] Errors announced: `role="alert"` (web) / `announceForAccessibility` (RN).
- [ ] Toast notifications announced + auto-dismissed after enough time to read.

## RN-Specific

- [ ] `accessibilityRole` set on every Pressable / View used as a control.
- [ ] `accessibilityLabel` on icon buttons.
- [ ] `accessibilityState` reflects disabled / selected / busy / checked / expanded.
- [ ] Decorative views: `accessibilityElementsHidden={true}` + `importantForAccessibility="no-hide-descendants"`.
- [ ] Group cohesive content with `accessible={true}` + combined `accessibilityLabel`.
- [ ] Focus management on route change + modal open via `AccessibilityInfo.setAccessibilityFocus`.
- [ ] Dynamic Type tested at AX5; layout doesn't break.
- [ ] `maxFontSizeMultiplier` set on tight UI elements.

## Internationalization (if multi-language)

- [ ] `<html lang="...">` set per page.
- [ ] React Navigation header titles localized.
- [ ] RTL support tested (Arabic / Hebrew / Persian if shipping).
- [ ] Locale-aware date / number formatting (`Intl.NumberFormat` / `Intl.DateTimeFormat`).

## Automated Tooling

- [ ] `eslint-plugin-jsx-a11y` (web) / `eslint-plugin-react-native-a11y` (RN) passes.
- [ ] Lighthouse accessibility score ≥ 95 on key pages.
- [ ] axe-core passes (zero serious + critical violations) via Playwright integration test.
- [ ] `react-axe` enabled in dev for every PR.

## Manual Testing

- [ ] **VoiceOver (iOS)** complete sign-in / browse / start-task / settings / sign-out flows.
- [ ] **TalkBack (Android)** same flows.
- [ ] **VoiceOver (macOS)** if web client.
- [ ] **NVDA (Windows)** if web client.
- [ ] **Keyboard-only** complete same flows on web (no mouse/trackpad).
- [ ] **iOS Dynamic Type AX5** — layout doesn't break on critical screens.
- [ ] **OS color filters** (Grayscale, Inverted Colors) tested on home screen.

## Pre-Launch Smoke

- [ ] All critical flows pass screen-reader test on iOS + Android.
- [ ] axe-core CI step is green.
- [ ] No serious / critical Lighthouse a11y violations.
- [ ] Real-user accessibility tester (employee / consultant) runs the flows once.

---

If any box is unchecked, document the reason in a tracking issue. Accessibility bugs ship for the lifetime of the app version.

## WCAG 2.2 — New Criteria (vs 2.1)

Verify these explicitly:

- [ ] **2.4.11 Focus Not Obscured (Min)** — focused element NOT entirely hidden by sticky header / cookie banner / floating buttons.
- [ ] **2.5.7 Dragging Movements** — every drag has a non-drag alternative (e.g., re-order list also via long-press menu).
- [ ] **2.5.8 Target Size (Min)** — 24×24 CSS px minimum.
- [ ] **3.2.6 Consistent Help** — help link in same place across pages.
- [ ] **3.3.7 Redundant Entry** — autofill prior info; don't make user re-type.
- [ ] **3.3.8 Accessible Authentication** — no "type 4 random characters from your password" puzzles.
