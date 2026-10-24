# OWASP MASVS L1 — Per-Requirement Checklist

OWASP MASVS v2.0 Level 1 covers the security baseline for all mobile apps. Higher levels (L2 = sensitive data, L3 = nation-state) layer on top. Most consumer apps meet L1.

Each requirement maps to a concrete check or implementation.

## MASVS-STORAGE — Secure Data Storage

- [ ] **MASVS-STORAGE-1**: The app uses an appropriate platform mechanism (Keychain / Keystore) to store sensitive data.
  - Tokens in `react-native-keychain`, never in `AsyncStorage` or unencrypted MMKV.
  - TOTP shared secrets NOT stored on the device — server-side only, KMS-encrypted.

- [ ] **MASVS-STORAGE-2**: The app does not write sensitive data to system logs or shared storage.
  - `console.*` stripped from release builds.
  - No `Log.d(TAG, sessionToken)`, no `NSLog(@"%@", token)`.
  - SQLite databases either NOT containing sensitive data, or encrypted (SQLCipher).
  - `android:allowBackup="false"` OR `<exclude domain="sharedpref" path="auth.xml" />` in backup rules.
  - iOS: sensitive Keychain items use `WHEN_UNLOCKED_THIS_DEVICE_ONLY` (not backed up).

## MASVS-CRYPTO — Cryptography

- [ ] **MASVS-CRYPTO-1**: The app uses cryptography for an explicit security need (no "encryption theater").
  - You can articulate WHY each crypto operation exists.
  - You're not "obfuscating" data with XOR or base64 and calling it encryption.

- [ ] **MASVS-CRYPTO-2**: The app uses current, industry-vetted cryptographic primitives.
  - AES-GCM, not AES-ECB.
  - Key derivation: PBKDF2 (≥600k iterations in 2026) or scrypt or Argon2.
  - No MD5, SHA-1, RC4, DES, 3DES.
  - No homegrown crypto.

## MASVS-AUTH — Authentication and Session Management

- [ ] **MASVS-AUTH-1**: The app uses secure authentication and authorization protocols.
  - See `auth-patterns` skill — passkeys / OAuth 2.1+PKCE / opaque sessions.
  - No HTTP Basic Auth.

- [ ] **MASVS-AUTH-2**: Local authentication (biometric / passcode) is invocable when needed.
  - `BIOMETRY_ANY_OR_DEVICE_PASSCODE` for app unlock.
  - Step-up auth for sensitive ops.

- [ ] **MASVS-AUTH-3**: The app secures sensitive operations and data with additional authentication.
  - Money transfers, password change, 2FA disable: re-prompt biometric or password.

## MASVS-NETWORK — Network Communication

- [ ] **MASVS-NETWORK-1**: The app secures all network traffic according to the current best practices.
  - HTTPS-only (TLS 1.2+; prefer TLS 1.3).
  - iOS ATS enabled, no exemption domains.
  - Android Network Security Config with `cleartextTrafficPermitted=false`.

- [ ] **MASVS-NETWORK-2**: The app performs identity pinning where applicable.
  - Pin SPKI hashes (current + backup key) for high-value endpoints.
  - OR: explicit decision to NOT pin, documented, with rationale.

## MASVS-PLATFORM — Platform Interaction

- [ ] **MASVS-PLATFORM-1**: The app uses IPC mechanisms securely.
  - Android: `exported="false"` on all Activities/Services/Receivers/Providers unless you mean to expose them.
  - iOS: URL scheme handlers validate input; no blind dispatch.

- [ ] **MASVS-PLATFORM-2**: The app only uses WebViews securely.
  - `setJavaScriptEnabled(true)` only when needed.
  - `setAllowFileAccess(false)`, `setAllowContentAccess(false)`, `setAllowFileAccessFromFileURLs(false)`.
  - Origin allowlist for `postMessage` recipients.
  - No mixing app credentials into WebView (cookies, localStorage).

- [ ] **MASVS-PLATFORM-3**: The app protects against deep-link / Intent injection.
  - Validate every deep-link param shape (regex / type guards).
  - Authentication-relevant deep links (magic link, password reset): single-use server-side, render confirmation UI before action.

## MASVS-CODE — Code Quality

- [ ] **MASVS-CODE-1**: The app requires up-to-date platform versions.
  - iOS deployment target ≥ 16 (covers passkeys + modern privacy APIs).
  - Android `minSdkVersion` ≥ 24, `targetSdkVersion` = current Play requirement (35 in 2026).

- [ ] **MASVS-CODE-2**: The app has a mechanism for forcing app updates.
  - Server returns a `min_app_version` header / endpoint.
  - Client refuses to function (or shows update prompt) when below.
  - Use force-update sparingly; only for security fixes.

- [ ] **MASVS-CODE-3**: The app is signed and provisioned correctly.
  - iOS: distribution certificate from your team, no jailbroken bypasses.
  - Android: Play App Signing enabled.

- [ ] **MASVS-CODE-4**: The app uses up-to-date third-party libraries with known vulnerabilities patched.
  - `yarn audit` / `npm audit` weekly, with a clear "no high-severity unfixed" policy.
  - Pin major versions; review minor/patch upgrades.
  - Cap transitive dependencies via `resolutions` in `package.json`.

## MASVS-RESILIENCE — Resilience

(L1 doesn't require RESILIENCE; included for completeness if you target L2.)

- **MASVS-RESILIENCE-1**: The app validates the integrity of the platform.
  - Optional root/jailbreak detection (JailMonkey).
  - Optional integrity attestation (Play Integrity API on Android, DeviceCheck / App Attest on iOS).

- **MASVS-RESILIENCE-2**: The app implements anti-tampering / anti-debug.
  - Optional. Most consumer apps skip. Add for high-value targets.

- **MASVS-RESILIENCE-3**: The app implements anti-static-analysis.
  - R8/ProGuard for Android (most apps).
  - iOS Swift code is harder to reverse than Obj-C; standard.
  - Don't bother with serious obfuscation unless threat model demands it.

- **MASVS-RESILIENCE-4**: The app detects and responds to runtime tampering.
  - Optional. Frida detection, debugger detection, etc. Brittle — best-effort.

## Production Verification

Before each release, run:

1. **MobSF** (`docker run -p 8000:8000 opensecurity/mobile-security-framework-mobsf:latest`) — upload the IPA / AAB and review the report.
2. **`yarn audit --groups dependencies` / `pnpm audit`** — fail the build on high-severity.
3. **`grep -r "console\." mobile/src/` after build** — should be zero in release bundle.
4. **Network capture with mitmproxy** in dev — verify TLS, no cleartext, no PII in URLs.
5. **Backup audit** — restore from iCloud / Google to a fresh device; verify no sensitive data crosses.

## Source Material

- OWASP — *MASVS v2.0*: <https://mas.owasp.org/MASVS/>
- OWASP — *MASTG*: <https://mas.owasp.org/MASTG/> (test cases per requirement)
- *MobSF* — automated scanner: <https://github.com/MobSF/Mobile-Security-Framework-MobSF>
- Apple — *Security Overview*: <https://support.apple.com/guide/security/welcome/web>
- Android — *App Security Best Practices*: <https://developer.android.com/topic/security/best-practices>
