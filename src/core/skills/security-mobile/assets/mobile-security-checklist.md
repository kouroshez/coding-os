# Mobile Security Pre-Submission Checklist

Run before TestFlight / Play Internal Testing. Each item is a concrete check; uncheck → block release.

## Storage

- [ ] All auth tokens stored via `react-native-keychain` (NOT `AsyncStorage`, NOT plain `MMKV`).
- [ ] Refresh tokens stored same way.
- [ ] OAuth tokens (Google/Apple ID tokens) NEVER persisted client-side after exchange.
- [ ] Per-install MMKV encryption key stored in Keychain (if encrypted MMKV used).
- [ ] PII in encrypted DB (SQLCipher) OR clearly classified as non-sensitive.
- [ ] No hardcoded API secrets in source / build artifacts.
- [ ] No `.env` checked into the repo (every dev key separate from prod).
- [ ] Backup excluded for sensitive files: iOS sets `WHEN_UNLOCKED_THIS_DEVICE_ONLY`; Android `<exclude>` rules set.

## Network

- [ ] HTTPS-only — `Info.plist` ATS unrelaxed.
- [ ] Android `network_security_config.xml` rejects cleartext traffic globally.
- [ ] Certificate pinning decision documented (pinned with rotation plan, OR explicit "not pinning, here's why").
- [ ] If pinning: 2 SPKI hashes (current + backup), pin failure shows recoverable error.
- [ ] No HTTP fallback for any API endpoint.
- [ ] mitmproxy / Charles dev test: only TLS traffic, no cleartext.
- [ ] No PII in URL query parameters (logs, history leak).
- [ ] No tokens in URL paths.

## Authentication

- [ ] Sign In with Apple offered if any other social provider is offered (App Store rule).
- [ ] OAuth flows use PKCE.
- [ ] OAuth callbacks open in native browser tab (Custom Tabs / SFSafariViewController), NOT WebView.
- [ ] Magic-link / password-reset deep links validate token shape before action.
- [ ] Magic-link / password-reset show confirmation UI before mutating state ("you'll sign in as user@example.com").
- [ ] Biometric prompt for app unlock with passcode fallback.
- [ ] Re-prompt biometric on background > 60 seconds (banking-style).
- [ ] Step-up authentication for sensitive ops (transfer, change password, disable 2FA).

## Permissions

- [ ] iOS: every permission has `NSXxxUsageDescription` explaining WHY.
- [ ] Android: every permission has clear justification; sensitive ones (BIND_ACCESSIBILITY_SERVICE, QUERY_ALL_PACKAGES) declared in Play Console form.
- [ ] Permissions requested in context, not on first launch.
- [ ] Soft-prompt before OS prompt for non-trivial permissions.
- [ ] No third-party SDK silently adding permissions you don't need (audit merged manifest).

## Code Quality

- [ ] `console.*` stripped from release builds (`babel-plugin-transform-remove-console`).
- [ ] Sensitive headers (Authorization) NOT logged by API client even in dev.
- [ ] Sentry / Crashlytics `beforeSend` scrubs PII.
- [ ] `__DEV__` guard around dev-only screens / panels (Reactotron, debug menus).
- [ ] No `debuggable=true` in release Android build.
- [ ] R8/ProGuard enabled with rules for native modules + reflection-using libs.
- [ ] iOS app NOT signed with development cert in release (Distribution cert from team).

## WebViews (if used)

- [ ] WebView allowlist of acceptable origins.
- [ ] `setAllowFileAccess(false)` (Android), `WKWebViewConfiguration.allowsContentJavaScript=true` only when needed (iOS).
- [ ] No app credentials (cookies / tokens) leaked into WebView origin.
- [ ] PostMessage handlers validate `event.origin`.

## Deep Links

- [ ] Universal Links / App Links configured (HTTPS-served, AASA + assetlinks.json verified).
- [ ] Custom-scheme fallback validated; no auth flows rely solely on `app://` scheme.
- [ ] Every deep-link param shape regex-validated.
- [ ] NotFound route catches malformed URLs without crashing.

## App-Switcher / Background

- [ ] Sensitive screens redact in `inactive` state (iOS app switcher).
- [ ] Optional: Android `FLAG_SECURE` on screens with extreme sensitivity.

## SDK / Dependency Audit

- [ ] `yarn audit` / `npm audit` passes with no high-severity issues.
- [ ] No new dependencies added without 1-paragraph justification in PR.
- [ ] Major-version locked in `package.json`; minor/patch reviewed before bump.
- [ ] No SDK that requests permissions unrelated to its job (analytics asking for location, etc.).

## Build / Release

- [ ] iOS: deployment target ≥ 16. Distribution cert + provisioning profile valid.
- [ ] Android: `targetSdkVersion` = current Play floor, `minSdkVersion` ≥ 24.
- [ ] App Bundle (`.aab`) for Play, IPA for App Store.
- [ ] Play App Signing enabled.
- [ ] dSYM (iOS) + mapping file (Android) uploaded to crash reporter for symbolication.
- [ ] No `* (Apple Wildcard)` provisioning profile in release build.
- [ ] No production API URL accidentally in dev build (and vice versa).

## Pre-Flight Verification

- [ ] **MobSF scan** of release build — no high-severity issues.
- [ ] **Filesystem audit** — install on test device, inspect app sandbox, confirm no plaintext tokens / PII.
- [ ] **Backup audit** — back up to iCloud/Google, restore on fresh device, confirm no sensitive data crosses.
- [ ] **mitmproxy capture** — only TLS, no PII in URLs, all expected headers present.
- [ ] **OS-level smoke** — VoiceOver/TalkBack passes on auth flows; Dynamic Type ≤ accessibility5 doesn't break.
- [ ] **Cold-start crash check** — install fresh, launch, verify no crash on the slowest supported device.

## Logout / Account Deletion

- [ ] Logout button visible in Settings.
- [ ] Logout calls server `/auth/logout` AND wipes Keychain AND resets Zustand stores AND navigates to sign-in.
- [ ] Account deletion path exists (App Store + Play Store BOTH require this).
- [ ] Account deletion confirms with "this is permanent" prompt.
- [ ] Account deletion server-side: revokes all sessions + refresh tokens, marks user `deleted_at`, schedules data purge per data-retention policy.

## Failure Surfaces

- [ ] Network failure shows actionable error (not "Error" with no detail).
- [ ] Pin failure shows "couldn't verify connection — please update".
- [ ] Sign-in failure shows generic "couldn't sign in" (no enumeration via "user not found" vs "wrong password").

---

If any box is unchecked, document the reason in a tracking issue with an ETA. Mobile security bugs ship for the lifetime of an app version — slow to recall, slow to update.
