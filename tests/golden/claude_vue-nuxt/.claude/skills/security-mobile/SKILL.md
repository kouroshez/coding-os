---
name: security-mobile
description: Mobile-specific security per OWASP MASVS v2 (Mobile Application Security Verification Standard). Use when designing or reviewing secure storage (Keychain/Keystore vs SharedPreferences/UserDefaults), certificate pinning, root/jailbreak detection, biometric authentication, deep-link injection defenses, IPC hardening, runtime application self-protection (RASP) basics. Targets React Native (bare) on iOS + Android. Pairs with auth-patterns (auth-side hardening) and security-web (server-side hardening).
tier: cross-cutting
domain: [mobile, security]
last_reviewed: "2026-05-11"

---

# Mobile Security — MASVS-Aligned Patterns

For React Native bare apps targeting iOS 16+ and Android 14+. Aligned with OWASP MASVS v2.0 (the 2024 update). Targets the realistic threat model of a consumer mobile app — not a banking app under nation-state attack, but a real app with payments, PII, and user accounts where a breach hurts.

## When to Use This Skill

- Storing tokens / credentials / secrets on the device.
- Choosing certificate pinning strategy (or whether to pin at all).
- Adding root/jailbreak detection.
- Designing biometric prompts for sensitive ops.
- Reviewing native-module surface area.
- Planning what NOT to log/screenshot/leak.
- Auditing third-party SDKs for risky permissions.
- Pre-flight before App Store / Play Store submission.

For server-side / API-side security, see `security-web`. For auth flows specifically, see `auth-patterns`.

## The Threat Model — Realistic Priorities

Mobile threat ranking for a consumer app (high → low priority):

1. **Lost device, no biometric / weak passcode** → app session compromised. Mitigation: biometric gate on launch + on sensitive ops; idle timeout; remote logout.
2. **Phishing → credential theft** → standard password takeover. Mitigation: passkeys (phishing-proof), magic-link with same-device check.
3. **Malicious / compromised library on the client** → can read in-memory state. Mitigation: minimize deps, audit weekly, prefer first-party libs.
4. **Insecure data at rest** → device backup or filesystem inspection leaks tokens / PII. Mitigation: Keychain/Keystore for all secrets, encrypted DB for sensitive PII.
5. **MITM on hostile networks** → tampered responses. Mitigation: TLS + (selectively) certificate pinning; refuse insecure connections.
6. **Reverse engineering for cloning / cheating** → app logic exposed. Mitigation: server-authoritative gameplay, minimal client trust, R8/ProGuard for Android.
7. **Replay of intercepted requests** → repeated actions. Mitigation: TLS, idempotency keys (api-design skill).
8. **Side-channel via screenshots / app switcher** → sensitive data leaks via screenshots, voice-over, etc. Mitigation: redact sensitive views in inactive state.

**NOT realistic for most consumer apps**: nation-state attackers, kernel-level malware, hardware tampering. Don't waste effort on these unless your threat model demands them.

## Secure Storage — MASVS L1 + L2

### What Goes Where

| Data | Where | Why |
|---|---|---|
| Auth session tokens / refresh tokens | **Keychain (iOS) / Keystore (Android)** via react-native-keychain | OS-level encryption, biometric gate available |
| OAuth tokens | Same as above | Same |
| Encryption keys you own | Keychain / Keystore | Same |
| TOTP shared secret | Server-side encrypted (KMS) — NOT on device | Device compromise = no 2FA bypass |
| User PII (name, email) | Encrypted DB (op-sqlite + SQLCipher) OR plain DB if not sensitive | Tradeoff |
| App preferences (theme, language) | MMKV / AsyncStorage (unencrypted) | Not sensitive |
| Cached server data | MMKV / SQLite / TanStack Query persister | Performance vs sensitivity tradeoff |
| Analytics queue | MMKV / file | Non-sensitive |
| **NEVER** | files in app sandbox (anyone with backup access reads), localStorage equivalents (AsyncStorage for tokens), URL params (history) | |

### Keychain (iOS) via react-native-keychain

```typescript
import * as Keychain from 'react-native-keychain';

// Store
await Keychain.setGenericPassword('session', sessionToken, {
  accessControl: Keychain.ACCESS_CONTROL.BIOMETRY_ANY_OR_DEVICE_PASSCODE,
  accessible:    Keychain.ACCESSIBLE.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  storage:       Keychain.STORAGE_TYPE.AES_GCM,
  service:       'com.app.session',  // namespace
});

// Retrieve (prompts biometric if required)
const creds = await Keychain.getGenericPassword({
  service: 'com.app.session',
  authenticationPrompt: { title: 'Unlock', subtitle: 'Use Face ID' },
});
const token = creds ? creds.password : null;

// Delete on logout
await Keychain.resetGenericPassword({ service: 'com.app.session' });
```

Key options:

- **`ACCESS_CONTROL.BIOMETRY_ANY_OR_DEVICE_PASSCODE`** — biometric required, passcode fallback. The right default for "unlock app" scenarios.
- **`ACCESS_CONTROL.BIOMETRY_CURRENT_SET`** — invalidates if user changes biometry (stronger; some legitimate cases like banking).
- **`ACCESSIBLE.WHEN_UNLOCKED_THIS_DEVICE_ONLY`** — readable only when device is unlocked, never backed up to iCloud/Google.
- **`STORAGE_TYPE.AES_GCM`** — symmetric AES; modern default.

### Android Keystore

react-native-keychain wraps Android Keystore automatically. The `accessControl` and `accessible` options translate to BIOMETRIC_STRONG and EncryptedSharedPreferences-style storage.

For raw access (rare): use `react-native-keychain` or `react-native-encrypted-storage`. NEVER `AsyncStorage` or `MMKV` (non-encrypted variant) for tokens.

### MMKV for Encrypted Non-Token Data

```typescript
import { MMKV } from 'react-native-mmkv';

// Encrypted instance (key derived per-install, stored in Keychain)
const secureKey = await getOrCreateMmkvKey();  // helper that uses Keychain
const encryptedMmkv = new MMKV({
  id: 'sensitive-cache',
  encryptionKey: secureKey,
});

encryptedMmkv.set('user_settings', JSON.stringify(settings));
```

For PII-heavy data (chat history, financial records), use SQLite with SQLCipher (op-sqlite supports this).

## TLS + Certificate Pinning

### TLS Baseline

- **HTTPS everywhere**. Refuse `http://` connections at the framework level.
- **iOS App Transport Security** (`Info.plist`):
  ```xml
  <key>NSAppTransportSecurity</key>
  <dict>
      <key>NSAllowsArbitraryLoads</key>
      <false/>
  </dict>
  ```
  Don't whitelist domains for ATS exception unless you have to (e.g., legacy partner API).
- **Android Network Security Config** (`res/xml/network_security_config.xml`):
  ```xml
  <network-security-config>
      <base-config cleartextTrafficPermitted="false">
          <trust-anchors>
              <certificates src="system" />
          </trust-anchors>
      </base-config>
  </network-security-config>
  ```
  Reference in `AndroidManifest.xml`: `android:networkSecurityConfig="@xml/network_security_config"`.

### Certificate Pinning — When to Pin

Pinning protects against rogue CAs (a real risk in some networks). It also creates BREAKAGE risk: if your cert rotates and the pinned hash is stale, every user is locked out.

**Pin when**:
- App handles money or PII at high stakes (banking, healthcare, authentication infrastructure).
- You can guarantee certificate rotation coordination (CI updates the app + the API in lockstep).

**Don't pin when**:
- Standard consumer app, no critical data flow.
- You can't operationally manage rotation (you'll DDoS yourself with broken updates).

### How to Pin

Pin the SUBJECT PUBLIC KEY HASH (SPKI), not the full certificate. SPKI survives cert rotation as long as you keep the same key.

```typescript
// react-native-ssl-pinning OR axios + custom adapter
import { fetch as pinnedFetch } from 'react-native-ssl-pinning';

const res = await pinnedFetch('https://api.app.com/lessons', {
  method: 'GET',
  sslPinning: {
    certs: ['cert-spki-sha256'],   // base64-encoded SHA-256 of SPKI
  },
  headers: { Authorization: `Bearer ${token}` },
});
```

**Pin two keys** (current + backup) so rotation is non-breaking. Generate the backup key, store it offline, swap to it during rotation.

### Pin Failure Behavior

DON'T just throw. Show user "Connection couldn't be verified — please update the app." Log to your error reporter. Provide an unpinned fallback if you have a graceful recovery path (most apps shouldn't).

## Biometric Auth (Local UX Gate, NOT Server Trust)

Biometrics on the client are a UX gate — they unlock locally-stored tokens. They are NOT proof to the server that the user is who they claim. The server still relies on the actual session token / WebAuthn signature.

```typescript
import * as Keychain from 'react-native-keychain';

async function unlockApp(): Promise<string | null> {
  try {
    const creds = await Keychain.getGenericPassword({
      service: 'com.app.session',
      authenticationPrompt: {
        title: 'Unlock',
        subtitle: 'Use Face ID to access your account',
        cancel: 'Use passcode',
      },
    });
    return creds ? creds.password : null;
  } catch (e: any) {
    if (e.code === 'AuthenticationFailed' || e.code === 'UserCanceled') {
      return null;
    }
    throw e;
  }
}
```

Re-prompt cadence:

- App cold launch → always.
- App backgrounded > 60 seconds → re-prompt.
- Sensitive op (transfer money, view 2FA codes) → re-prompt every time.

## Detecting Root / Jailbreak

OWASP MASVS L2: should detect tampered runtime. For most consumer apps this is overkill; add when:

- App handles money or compliance-required data.
- You've seen abuse from rooted devices.

```typescript
import JailMonkey from 'jail-monkey';

if (JailMonkey.isJailBroken()) {
  // Soft block: warn user, refuse to enable sensitive features.
  // Hard block: refuse to launch (some banks do this; loses legitimate users with rooted dev devices).
}
```

JailMonkey checks: presence of `Cydia.app` (iOS), `su` binary (Android), busybox, write to `/system`, etc. Not bulletproof — determined attackers bypass it. Use as a deterrent + a server-side signal (clients with elevated risk get extra verification).

## Deep Link Injection

Deep links can carry malicious payloads. Validate every parameter:

```typescript
// linking.ts
config: {
  screens: {
    Lesson: {
      path: 'lessons/:lessonId',
      parse: {
        lessonId: (raw: string) => {
          if (!/^lsn_[a-zA-Z0-9]{8,32}$/.test(raw)) {
            throw new Error('invalid lesson id');
          }
          return raw;
        },
      },
    },
    PasswordReset: {
      path: 'auth/reset/:token',
      parse: {
        token: (raw: string) => {
          if (!/^[A-Za-z0-9_-]{32,128}$/.test(raw)) {
            throw new Error('invalid reset token');
          }
          return raw;
        },
      },
    },
  },
},
```

For deep links that authenticate the user (magic link, password reset), additional rules:

- Reject if NOT served via HTTPS app link (refuse custom scheme for these).
- Server-side: token is single-use, short-lived, scoped to action.
- Client: render a "this will sign you in as user@example.com — confirm?" screen before action; defeat clickjacking.

## App Switcher / Background Redaction

iOS takes a screenshot for the app switcher. If sensitive data is on screen, the screenshot lives in the cache.

```typescript
import { useEffect, useState } from 'react';
import { AppState } from 'react-native';

export function useBackgroundRedaction(): boolean {
  const [redact, setRedact] = useState(false);
  useEffect(() => {
    const sub = AppState.addEventListener('change', (s) => {
      // 'inactive' is the correct trigger for the switcher screenshot.
      setRedact(s !== 'active');
    });
    return () => sub.remove();
  }, []);
  return redact;
}

// In sensitive screens:
const redact = useBackgroundRedaction();
return redact ? <RedactedView /> : <RealView />;
```

Android: optionally `setFlags(WindowManager.LayoutParams.FLAG_SECURE)` to prevent screenshots and screen recording entirely. Use sparingly — frustrating in normal use.

## Logging Hygiene

NEVER log:

- Auth tokens (Authorization header, cookies).
- Passwords (even hashed).
- TOTP codes / backup codes.
- Session IDs.
- PII: full names, emails, phone, addresses, payment details, government IDs.
- Long IDs that uniquely identify users (use a hash or a short stub).

Patterns to enforce:

```typescript
// Strip sensitive headers from API client logs.
api.interceptors.request.use((cfg) => {
  if (__DEV__) console.log('[api]', cfg.method, cfg.url);  // NO body, NO headers
  return cfg;
});

// In the framework error reporter:
Sentry.init({
  beforeBreadcrumb(breadcrumb) {
    if (breadcrumb.category === 'http') {
      delete breadcrumb.data?.request_body;
      delete breadcrumb.data?.response_body;
    }
    return breadcrumb;
  },
  beforeSend(event) {
    return scrubPII(event);
  },
});

// Strip in release builds:
// babel-plugin-transform-remove-console: removes all console.* in production.
```

## SDKs — Audit Risky Permissions

Many third-party SDKs request more than they need. On every dependency add:

1. Read the SDK's permission requirements.
2. Verify in the merged manifest (`./gradlew app:dependencies` + look at the rendered AndroidManifest).
3. Check for: `READ_PHONE_STATE`, `ACCESS_FINE_LOCATION`, `READ_CONTACTS`, `RECORD_AUDIO`, `READ_EXTERNAL_STORAGE`, `BIND_ACCESSIBILITY_SERVICE`.
4. If the SDK adds a permission your app doesn't need, find an alternative or use the manifest `<uses-permission tools:node="remove" />` to strip it.

Common offenders: certain ad SDKs, some analytics SDKs, push notification wrappers that ask for location. Stick to first-party / well-known options when possible (Firebase, Sentry, Notifee).

## Native Module Surface — Threat Vector

A native module is direct OS access from JS. Audit yours and any third-party ones for:

- Arbitrary file read/write (a malicious JS could exfiltrate any file the app can read).
- Arbitrary command execution (`exec`, `Runtime.exec`).
- Network calls bypassing your TLS config.
- Plain-text credential storage.

For modules you write: validate inputs at the JS↔native boundary; never trust JS-side strings/numbers.

```swift
// iOS
@objc(set:value:resolve:reject:)
func set(_ key: String, value: String, resolve: ..., reject: ...) {
  guard key.count <= 256, value.count <= 16384 else {
    reject("BAD_INPUT", "size limit", nil)
    return
  }
  // ... safe operation
}
```

## Pre-Submission Security Review

Use [assets/mobile-security-checklist.md](assets/mobile-security-checklist.md) before TestFlight/Play Internal. Run an automated scan with **MobSF** (Mobile Security Framework) on the release build — catches common issues (cleartext traffic, debuggable=true, weak crypto).

For more thorough audit: OWASP MASVS L1 covers consumer apps; L2 + L3 are for high-risk apps (banking, government).

## Common Mobile-Security Mistakes

1. **Tokens in AsyncStorage / unencrypted MMKV** — trivially read via filesystem inspection or backup.
2. **TOTP secret on device** — device compromise = 2FA bypass.
3. **No biometric prompt for sensitive ops** — lost-phone scenario gives full access.
4. **Pinning without rotation strategy** — DDoS yourself the day cert renews.
5. **Pin failure throws raw error** — confuses users who can't update.
6. **Deep-link params not validated** — path traversal, SQLi via QR code.
7. **Logging Authorization header** in production traces — leaks session tokens to Sentry / Crashlytics.
8. **Sensitive views not redacted on background** — screenshot cache leak.
9. **Backup not excluded for sensitive files** — iCloud / Google backup = data leak.
10. **Debuggable=true in release** — anyone can attach a debugger and inspect memory.
11. **No R8/ProGuard** on Android release — class names leaked, easier reversing.
12. **Trusting client-side auth flags** — `if (user.isAdmin)` on the client is meaningless; server must check.
13. **Cleartext fallback in network config** — defeats TLS purpose.
14. **WebView with `setAllowFileAccess(true)`** — trivial file read from page JS.
15. **Insecure WebView origin checks** — postMessage from any page wins.

## Source Material

- *OWASP MASVS v2.0* (2024 release) — primary standard.
- *OWASP MSTG* (Mobile Security Testing Guide) — practical patterns per requirement.
- Apple — *App Security Overview* + *Keychain Services Programming Guide*.
- Android — *App Security Best Practices* + *Network Security Configuration*.
- *MobSF* (Mobile Security Framework) — automated scanner.
- React Native Security: <https://reactnative.dev/docs/security>
