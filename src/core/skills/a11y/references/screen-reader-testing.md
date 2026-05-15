# Screen Reader Testing — Practical Protocol

The shortest path to genuine accessibility confidence: turn on a screen reader, complete the critical flows eyes-closed, fix every place you got stuck.

## Setup — Per Platform

### macOS — VoiceOver

- **Toggle**: `Cmd + F5` (or triple-tap Touch ID).
- **VO key**: `Caps Lock` (a.k.a. "VO"). Press with arrows to navigate.
- **Quick start**:
  - VO + A → read all
  - VO + Right Arrow → next item
  - VO + Space → activate
  - VO + Shift + Down Arrow → enter group
  - Tab → next interactive
  - VO + U → rotor (jump by headings, links, etc.)

### iOS — VoiceOver

- **Toggle**: Settings → Accessibility → VoiceOver. OR triple-press the home/side button (Settings → Accessibility → Accessibility Shortcut).
- **Gestures**:
  - Single tap → focus + announce
  - Double tap → activate
  - Swipe right / left → next / previous element
  - Two-finger swipe up → read all from top
  - Three-finger swipe → scroll
  - Two-finger Z (rotor scrub) → cycle reading mode
- **Rotor**: two-finger twist → switch between Words / Characters / Headings / Links / etc.

### Windows — NVDA (free, recommended)

- **Install**: <https://www.nvaccess.org/download/>
- **Toggle**: launches in system tray; `Insert + Q` to quit.
- **NVDA key**: `Insert` (configurable to Caps Lock).
- **Quick start**:
  - NVDA + Down → read all
  - Down arrow → next line
  - Tab → next interactive
  - H → next heading (NVDA browse mode)
  - F → next form field
  - K → next link
  - NVDA + Space → toggle Browse / Focus mode

### Android — TalkBack

- **Toggle**: Settings → Accessibility → TalkBack. Or hold both volume buttons (Settings → Accessibility → Volume key shortcut).
- **Gestures**:
  - Tap once → focus + announce
  - Double-tap → activate
  - Swipe right / left → next / previous
  - Swipe down + right → open TalkBack menu
  - Two-finger swipe → scroll

### Chrome — ChromeVox (dev only)

- Extension; not real VO/NVDA. OK for quick checks; don't ship-test on it alone.

## The Test Protocol

For each critical flow: **complete the entire flow with the screen on, but don't look at it.** If you get stuck or can't complete, that's a bug.

### Flow 1: Sign-in

- Launch app → screen reader announces page title.
- Find the email field via swipe or rotor.
- Type email (use keyboard / external keyboard preferred).
- Find password field, type.
- Find sign-in button, activate.
- On success → land on home; SR announces home page title.
- On failure → SR announces error inline.

**Common failures**:
- Inputs without labels → SR reads "edit text" without context.
- Errors not announced → user submits, hears nothing, doesn't know.
- Sign-in button activates but loading state isn't announced → user re-taps.

### Flow 2: Main Navigation

- Tab / swipe through nav items at the top.
- SR announces "Home, tab, 1 of 3 selected" / "Lessons, tab" / etc.
- Activate each tab; SR announces new context.

**Common failures**:
- Tab role missing → SR reads as plain button.
- Selected state not announced.
- Tab change doesn't refocus content area.

### Flow 3: List Browse + Item Open

- Scroll list with SR.
- SR reads each item including state ("Hexagons, completed" / "Setup, not started").
- Activate one.
- Detail screen opens; SR announces title.

**Common failures**:
- List items don't include state.
- After tapping, SR stays on the list (no focus shift).
- Long list never reaches the end with SR (focus loss).

### Flow 4: Form Submission

- Open form.
- SR announces required fields.
- Fill all fields; on each, SR re-announces validity.
- Submit.
- On error → SR announces summary and focuses first invalid field.
- On success → SR announces success.

**Common failures**:
- Required not announced.
- Errors visible but not announced.
- Focus stays on submit button after error.

### Flow 5: Modal / Dialog

- Trigger modal.
- SR announces modal title + role.
- Focus is inside modal (verify by trying to navigate out — Esc / back closes).
- Cancel and Confirm buttons reachable.
- After close, focus returns to trigger.

**Common failures**:
- Focus stays on the page behind.
- No focus trap → user navigates to underlying content.
- Close doesn't return focus.

### Flow 6: Settings + Sign-out

- Reach settings via main nav.
- Toggle a setting (e.g., notifications).
- SR announces new state ("On" / "Off").
- Sign out button activates; redirected to sign-in.

## Mobile-Specific Flows

For RN apps, ALSO check:

### Push Notification Tap → App Opens to Specific Screen

- Receive a notification.
- Tap with screen reader on.
- App opens; SR announces the destination screen title.
- Back goes to the screen you'd expect (typically Home).

### Background → Foreground

- App in foreground.
- Switch to another app, come back.
- SR re-announces context (page title) on resume.

### Biometric Prompt

- Trigger Face ID / Touch ID / fingerprint.
- SR announces the prompt purpose ("Use Face ID to sign in").
- Cancel works; falls back to passcode.

### Modal from Notification

- Tap in-app notification.
- Modal opens; SR announces and focuses correctly.

## Common Issues + How to Spot Them

| Symptom | Likely cause |
|---|---|
| SR reads "button" with no context | Missing `accessibilityLabel` / `aria-label` |
| SR reads filename ("logo.png") | Missing `alt` / `accessibilityLabel` on image |
| SR skips an element you can see | Element has `aria-hidden` / `accessibilityElementsHidden` set wrongly |
| SR reads same text twice | Both visible Text and aria-label are set |
| Cannot reach element via swipe | Element is not focusable or `tabindex="-1"` blocks |
| Activated but nothing happens | Button doesn't have proper role; `onPress` not wired |
| User stuck after page change | No focus management on route change |
| Live update silent | Missing `aria-live` / `accessibilityLiveRegion` / `announceForAccessibility` |
| Tab order is weird | DOM doesn't match visual; explicit `tabindex` overriding |

## Test Cadence

- **Per-feature PR**: dev runs SR briefly on the new screen.
- **Per-sprint**: QA runs SR through one critical flow start-to-finish.
- **Per-release**: full SR test of all critical flows on iOS + Android.
- **Annual**: external accessibility audit (good practice; legal cover in regulated industries).

## Source Material

- Apple — *Test Accessibility on Your Device with VoiceOver*: <https://developer.apple.com/library/archive/technotes/TestingAccessibilityOfiOSApps/TestAccessibilityonYourDevicewithVoiceOver/TestAccessibilityonYourDevicewithVoiceOver.html>
- Android — *Test your app's accessibility*: <https://developer.android.com/guide/topics/ui/accessibility/testing>
- WebAIM — *VoiceOver Quick Reference*: <https://webaim.org/articles/voiceover/>
- WebAIM — *NVDA Quick Reference*: <https://webaim.org/articles/nvda/>
- *Empathy Lab* — disability simulation tools at Slack / Google for periodic team practice.
