# Mobile Launch Checklist (App Store + Play Store)

Run before submitting to TestFlight / Play Internal Testing. Each item maps to a documented store rule or common rejection reason.

## App Store Connect (iOS)

### Account / Privacy

- [ ] **In-app account deletion** (App Review Guideline 5.1.1(v)) — must be reachable in Settings, must actually delete (not deactivate).
- [ ] **Sign In with Apple** offered if any 3rd-party login is offered (Guideline 4.8).
- [ ] **App Privacy section filled** in App Store Connect — every category of data collected.
- [ ] **Privacy manifest (`PrivacyInfo.xcprivacy`)** included for required-reason APIs (UserDefaults, file timestamps, system boot time, disk space, active keyboard).
- [ ] **Tracking permission** (App Tracking Transparency) requested before any cross-app tracking.
- [ ] **Privacy nutrition labels** match what the app actually does.

### Permissions / Plist

Every permission requires `NSXxxUsageDescription` in `Info.plist` explaining WHY:

- [ ] `NSCameraUsageDescription`
- [ ] `NSPhotoLibraryUsageDescription` (read) / `NSPhotoLibraryAddUsageDescription` (write)
- [ ] `NSMicrophoneUsageDescription`
- [ ] `NSLocationWhenInUseUsageDescription` / `NSLocationAlwaysAndWhenInUseUsageDescription`
- [ ] `NSContactsUsageDescription`
- [ ] `NSCalendarsUsageDescription`
- [ ] `NSFaceIDUsageDescription`
- [ ] `NSUserTrackingUsageDescription`
- [ ] `NSBluetoothAlwaysUsageDescription`

### App Capabilities

- [ ] **Associated Domains** capability set with `applinks:app.com` + `webcredentials:app.com`.
- [ ] **Push Notifications** capability if used.
- [ ] **Background Modes** flagged ONLY for what you actually use (audio / location / fetch / remote-notification).
- [ ] **App Groups** if sharing data with extension.

### Submission

- [ ] **App icons** for every required size (1024×1024 marketing + all device sizes).
- [ ] **Launch storyboard / screen** that doesn't look like a loading screen.
- [ ] **Demo account** for reviewers (login + password) in App Review notes.
- [ ] **Reviewer instructions** for any flow that requires backend setup.
- [ ] **No dev tooling** left in the build (Reactotron, Flipper, Wormholy if used in dev).
- [ ] **Content rating** filled (sex, violence, profanity, gambling).
- [ ] **Export compliance** answered (uses encryption? exempt? has documentation?).
- [ ] **TestFlight build** smoke-tested by 3+ team members on real devices.

### Common Rejection Triggers

- [ ] **No web-view-only "thin wrapper"** — Guideline 4.2 needs native value-add.
- [ ] **No "log in or skip"** if functionality works without an account.
- [ ] **No links to external payment** for digital goods (Guideline 3.1.1).
- [ ] **No alpha/beta language** in App Store description ("preview", "beta", "test").
- [ ] **Crash-free at launch** on the oldest supported iOS version (test with `xcrun simctl`).
- [ ] **No placeholder content** ("Lorem ipsum", "TODO").

## Google Play (Android)

### Account / Privacy

- [ ] **In-app account deletion** OR a clear web URL for it, posted in store listing (Play policy from May 2024).
- [ ] **Data safety form** completed in Play Console — every data type collected/shared.
- [ ] **Privacy policy URL** in store listing.
- [ ] **Permissions declarations form** for sensitive permissions (SMS, Call Log, Background Location, Accessibility Service).

### Permissions / Manifest

- [ ] Every permission in `AndroidManifest.xml` has a documented justification.
- [ ] `BIND_ACCESSIBILITY_SERVICE` only if app is genuinely an accessibility tool (or you have explicit Play exemption).
- [ ] `QUERY_ALL_PACKAGES` only if you genuinely need to query all installed apps.
- [ ] `READ_MEDIA_IMAGES` / `READ_MEDIA_VIDEO` / `READ_MEDIA_AUDIO` instead of `READ_EXTERNAL_STORAGE` on API 33+.
- [ ] Foreground service has the right `foregroundServiceType` declared (data sync / location / phone-call / etc.).

### Build

- [ ] **App Bundle (`.aab`)**, not `.apk`.
- [ ] **Play App Signing** enabled.
- [ ] **R8 / ProGuard** enabled with rules for native modules + reflection-using libs.
- [ ] **`targetSdkVersion`** ≥ current Play requirement (35 in 2026).
- [ ] **`compileSdkVersion`** = `targetSdkVersion` or newer.
- [ ] **`minSdkVersion`** ≥ 24 (covers >97% of devices).
- [ ] **64-bit native libraries** included (Play rejects 32-bit-only since 2019).
- [ ] **Debuggable false** in release builds.
- [ ] **App links verification** passes (`adb shell pm get-app-links com.app` shows `verified`).

### Submission

- [ ] **App icon, feature graphic, screenshots** (phone + tablet) in store listing.
- [ ] **Short description ≤ 80 chars**, full description ≤ 4000 chars.
- [ ] **Content rating** completed via IARC questionnaire.
- [ ] **Target audience and content** wizard completed (especially careful for under-13).
- [ ] **Designed for Families** opt-in only if you genuinely target kids (extra restrictions).
- [ ] **Test on a real device** with multiple Android versions (24, 30, 33, 35).

## Cross-Platform

- [ ] **Crash reporting** wired up (Sentry / Crashlytics) with sourcemaps + dSYMs uploaded to symbolicate.
- [ ] **Analytics consent flow** in EU/UK (GDPR), US (CPRA where applicable).
- [ ] **No console.log spam** in release builds (`babel-plugin-transform-remove-console`).
- [ ] **API base URL** is the prod URL in release builds (not staging / not localhost).
- [ ] **No debug keys** in release config (RevenueCat dev key, Sentry dev DSN, etc.).
- [ ] **Version + build number** bumped (`CFBundleShortVersionString` / `CFBundleVersion`, `versionName` / `versionCode`).
- [ ] **App startup time < 2s** on a mid-tier device (Pixel 6, iPhone 12).
- [ ] **App size < 100MB** (compressed) — over this requires Play asset delivery / iOS on-demand resources.
- [ ] **Push notifications tested** — both fresh launch and backgrounded states.
- [ ] **Deep links tested** — universal/app links route correctly even from cold start.
- [ ] **Offline behavior tested** — toggle airplane mode mid-flow and verify graceful degradation.
- [ ] **Background → foreground transition** doesn't crash, lose state, re-fetch unnecessarily.
- [ ] **Locale / RTL** tested if you support multiple languages.
- [ ] **Accessibility** tested with VoiceOver (iOS) + TalkBack (Android) on at least the main flows.
- [ ] **Dark mode** doesn't break readability anywhere.
- [ ] **Tablet / large screen** at least minimally usable (Apple/Google both penalize stretched-phone UI).

## Operations

- [ ] **Release notes** drafted for both stores (markdown stripped; plain text only).
- [ ] **Rollback plan** documented (Play has staged rollouts; App Store has phased release).
- [ ] **Monitoring dashboards** primed: crash rate, ANR rate, slow rendering, network errors.
- [ ] **On-call** assigned for first 48 hours post-release.
- [ ] **Marketing / support team** notified of feature changes before users start asking.

## Post-Launch (First 7 Days)

- [ ] Crash-free user sessions ≥ 99.5% on both platforms.
- [ ] No spike in 1-star reviews mentioning crashes / login issues / payment.
- [ ] Sync queue success rate ≥ 99% (failed mutations are real bugs).
- [ ] Push delivery success ≥ 95% for users with valid tokens.
- [ ] No App Store / Play violation emails.

If any post-launch metric fails, have a hotfix path ready (OTA for non-native fixes; emergency store release for native).
